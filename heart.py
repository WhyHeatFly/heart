"""粉心流光（pygame 版）：光头边画爱心边缩小，画出向内收的心形螺旋，沿途射出长拖线粒子，运行 python3 heart.py，Esc 退出"""
import math
import random
import sys

import pygame

WIDTH, HEIGHT = 900, 780
FPS = 60
TAU = 2 * math.pi

# 颜色
BG = (5, 2, 16)
WHITE = (255, 255, 255)
PINK = (255, 125, 195)
HOT_PINK = (255, 60, 150)
PURPLE = (165, 120, 255)
CYAN = (110, 185, 255)
OUTLINE = (235, 220, 255)        # 轮廓线颜色
GRADIENT = (PINK, PURPLE, CYAN)  # 粒子从上到下的配色
PALETTE_SIZE = 48
LEVELS = 10                      # 光斑亮度分级，用于缓存

# 心形参数
HEART_SCALE = 18
HEART_SAMPLES = 900
HCX, HCY = WIDTH / 2, HEIGHT / 2 - 2.5 * HEART_SCALE
HEART_SPEED = 4                  # 光头每帧前进的采样点数
TRAIL_MAX = 380                  # 光头后面加亮的长度
HEAD_LEN = 90                    # 光头后面偏白、更粗的一段
OUTLINE_LEN = 1350               # 淡轮廓线保留的长度，超过一圈时能看到上一圈的大爱心
OUTLINE_LEVEL = 0.55             # 淡轮廓线的亮度

# 边画边缩小：光头走 SHRINK_LAPS 圈从原大小平滑缩到 MIN_SCALE，再走 GROW_LAPS 圈平滑放大回去
MIN_SCALE = 0.55
SHRINK_LAPS = 3
GROW_LAPS = 1

# 射线粒子
MAX_PARTICLES = 700
SPAWN_RATE = 6                   # 每帧新生粒子数
SPAWN_RANGE = 320                # 粒子在光头后方多远的范围内产生
PARTICLE_LIFE = (60, 120)        # 帧
PARTICLE_SPEED = (1.5, 7.0)
SPREAD = 0.3                     # 偏离法线的角度标准差，弧度
INWARD_RATIO = 0.08              # 向心内射出的比例
SPARK_RATIO = 0.5                # 末端是十字星的比例
DRAG = 0.975

# 轮廓上的粉色光珠
MAX_BEADS = 160
BEAD_RATE = 2                    # 每帧新生光珠数
BEAD_LIFE = (110, 200)
BEAD_SIZE = (3, 6)

# 贴着当前轮廓内侧闪烁的小白点
EDGE_SPARKLES = 320

# 光头每画完一圈，沿刚画完的这一圈同时爆开一次
RING_BURST_STEP = 5
RING_BURST_SPEED = 1.6

# 爱心中间的文字，位置固定，不随爱心缩放
TEXT_LINES = ("好好吃饭，天天开心！",)
TEXT_SIZES = (28,)
TEXT_GAP = 10
TEXT_COLOR = (255, 215, 235)
TEXT_Y = HCY - 20                # 文字块的垂直中心，这个位置离最小一圈爱心的轮廓最远
FONT_PATHS = (
    "C:/Windows/Fonts/msyh.ttc",     # Windows：微软雅黑
    "C:/Windows/Fonts/simhei.ttf",   # Windows：黑体
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
)

# 背景与泛光
STAR_COUNT = 140
BLOOM_PASSES = 1


def heart_point(t):
    """心形参数方程，t=0 为顶部凹口，t=π 为心尖"""
    x = 16 * math.sin(t) ** 3
    y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
    return HCX + x * HEART_SCALE, HCY + y * HEART_SCALE


def load_font(size):
    """依次尝试系统中文字体，都没有时退回 SysFont"""
    for path in FONT_PATHS:
        try:
            return pygame.font.Font(path, size)
        except OSError:
            continue
    return pygame.font.SysFont("microsoftyahei,simhei,pingfangsc,hiraginosansgb,stheiti,arialunicodems", size)


def scale_at(g):
    """光头走到累计进度 g（采样点数）时爱心的大小，随进度连续变化"""
    u = (g / HEART_SAMPLES) % (SHRINK_LAPS + GROW_LAPS)
    w = u / SHRINK_LAPS if u < SHRINK_LAPS else 1 - (u - SHRINK_LAPS) / GROW_LAPS
    return MIN_SCALE + (1 - MIN_SCALE) * (0.5 + 0.5 * math.cos(math.pi * w))


def lerp(a, b, u):
    return tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))


def scale_color(color, k):
    k = max(0.0, min(1.0, k))
    return (int(color[0] * k), int(color[1] * k), int(color[2] * k))


def gradient(u):
    seg = u * (len(GRADIENT) - 1)
    i = min(int(seg), len(GRADIENT) - 2)
    return lerp(GRADIENT[i], GRADIENT[i + 1], seg - i)


PALETTE = [gradient(i / (PALETTE_SIZE - 1)) for i in range(PALETTE_SIZE)]

_glow_cache = {}


def glow(color, radius):
    """径向渐变光斑，配合 BLEND_ADD 叠加；按 (颜色, 半径) 缓存"""
    key = (color, radius)
    sprite = _glow_cache.get(key)
    if sprite is None:
        sprite = pygame.Surface((radius * 2, radius * 2)).convert()
        sprite.fill((0, 0, 0))
        for r in range(radius, 0, -1):
            pygame.draw.circle(sprite, scale_color(color, (1 - r / radius) ** 2), (radius, radius), r)
        _glow_cache[key] = sprite
    return sprite


def add_glow(surface, color, radius, x, y):
    surface.blit(glow(color, radius), (x - radius, y - radius), special_flags=pygame.BLEND_ADD)


class Particle:
    __slots__ = ("ox", "oy", "x", "y", "vx", "vy", "life", "max_life", "color", "size", "spark")


class Bead:
    __slots__ = ("x", "y", "life", "max_life", "color", "size")


class Scene:
    def __init__(self):
        self.base = [heart_point(TAU * i / HEART_SAMPLES) for i in range(HEART_SAMPLES)]
        ys = [y for _, y in self.base]
        top, bottom = min(ys), max(ys)
        self.color_idx = [round((y - top) / (bottom - top) * (PALETTE_SIZE - 1)) for y in ys]
        self.normals = [self._normal(i) for i in range(HEART_SAMPLES)]
        self.stars = [(random.uniform(0, WIDTH), random.uniform(0, HEIGHT), random.uniform(0, TAU),
                       random.uniform(0.01, 0.05), random.choice((1, 1, 1, 2)),
                       random.choice((WHITE, PINK, CYAN))) for _ in range(STAR_COUNT)]
        self.sparkles = []
        for _ in range(EDGE_SPARKLES):
            i = random.randrange(HEART_SAMPLES)
            (x, y), (nx, ny) = self.base[i], self.normals[i]
            d = -random.uniform(2, 10)
            self.sparkles.append((x + nx * d, y + ny * d, random.uniform(0, TAU), random.uniform(0.04, 0.15)))
        self.particles = []
        self.beads = []
        self.head = 0
        self.frame = 0
        self.light = pygame.Surface((WIDTH, HEIGHT)).convert()
        self.background = self._background()
        self.vignette = self._vignette()
        self.text = self._text_layer()

    def _normal(self, i):
        """轮廓在 i 处朝外的单位法线，等比缩放后方向不变"""
        (x0, y0), (x1, y1) = self.base[i - 1], self.base[(i + 1) % HEART_SAMPLES]
        tx, ty = x1 - x0, y1 - y0
        length = math.hypot(tx, ty) or 1
        nx, ny = ty / length, -tx / length
        px, py = self.base[i]
        if nx * (px - HCX) + ny * (py - HCY) < 0:
            nx, ny = -nx, -ny
        return nx, ny

    @staticmethod
    def at(x, y, s):
        """基准坐标按缩放 s 映射到屏幕"""
        return HCX + (x - HCX) * s, HCY + (y - HCY) * s

    def point(self, g):
        """光头在累计进度 g 时所在的屏幕位置"""
        return self.at(*self.base[g % HEART_SAMPLES], scale_at(g))

    @staticmethod
    def _background():
        """底色加一团很淡的中心紫光"""
        bg = pygame.Surface((WIDTH, HEIGHT)).convert()
        bg.fill(BG)
        add_glow(bg, (30, 10, 50), 420, int(HCX), int(HCY))
        return bg

    @staticmethod
    def _text_layer():
        """文字预先画好，每帧叠加到光层上，和其他光一起泛光"""
        layer = pygame.Surface((WIDTH, HEIGHT)).convert()
        layer.fill((0, 0, 0))
        lines = [load_font(size).render(text, True, TEXT_COLOR) for text, size in zip(TEXT_LINES, TEXT_SIZES)]
        total = sum(s.get_height() for s in lines) + TEXT_GAP * (len(lines) - 1)
        y = TEXT_Y - total / 2
        for s in lines:
            layer.blit(s, (HCX - s.get_width() / 2, y))
            y += s.get_height() + TEXT_GAP
        return layer

    @staticmethod
    def _vignette():
        """四周压暗，用 BLEND_MULT 叠加"""
        v = pygame.Surface((WIDTH, HEIGHT)).convert()
        v.fill((90, 90, 90))
        far = int(math.hypot(WIDTH, HEIGHT) / 2)
        for r in range(far, 0, -4):
            k = 90 + 165 * min(1.0, (1 - r / far) * 2.2)
            pygame.draw.circle(v, (k, k, k), (WIDTH // 2, HEIGHT // 2), r)
        return v

    def spawn(self, g, speed_scale=1.0, inward_ok=True):
        """从进度 g 处的轮廓点射出一个粒子"""
        i = g % HEART_SAMPLES
        nx, ny = self.normals[i]
        speed = random.uniform(*PARTICLE_SPEED) * speed_scale
        if inward_ok and random.random() < INWARD_RATIO:
            nx, ny, speed = -nx, -ny, speed * 0.35
        angle = math.atan2(ny, nx) + random.gauss(0, SPREAD)
        p = Particle()
        p.ox, p.oy = self.point(g)
        p.x, p.y = p.ox, p.oy
        p.vx, p.vy = speed * math.cos(angle), speed * math.sin(angle)
        p.life = p.max_life = random.randint(*PARTICLE_LIFE)
        p.color = PALETTE[self.color_idx[i]]
        p.size = random.choice((2, 2, 3, 3, 4))
        p.spark = random.random() < SPARK_RATIO
        self.particles.append(p)

    def spawn_bead(self, g):
        """光珠落在进度 g 处的轮廓旁，之后位置固定"""
        i = g % HEART_SAMPLES
        x, y = self.point(g)
        nx, ny = self.normals[i]
        d = random.uniform(-6, 6)
        b = Bead()
        b.x, b.y = x + nx * d, y + ny * d
        b.life = b.max_life = random.randint(*BEAD_LIFE)
        b.color = lerp(PALETTE[self.color_idx[i]], HOT_PINK, 0.35)
        b.size = random.randint(*BEAD_SIZE)
        self.beads.append(b)

    def step(self):
        self.frame += 1
        prev = self.head
        self.head += HEART_SPEED
        if self.head // HEART_SAMPLES != prev // HEART_SAMPLES:
            for g in range(self.head - HEART_SAMPLES, self.head, RING_BURST_STEP):
                self.spawn(g, RING_BURST_SPEED, inward_ok=False)

        reach = min(SPAWN_RANGE, self.head)
        for _ in range(SPAWN_RATE):
            if len(self.particles) < MAX_PARTICLES:
                back = int(random.random() ** 2 * reach)  # 越靠近光头越密
                self.spawn(self.head - back)
        for _ in range(BEAD_RATE):
            if len(self.beads) < MAX_BEADS:
                self.spawn_bead(self.head - random.randint(0, reach))

        alive = []
        for p in self.particles:
            p.x += p.vx
            p.y += p.vy
            p.vx *= DRAG
            p.vy *= DRAG
            p.life -= 1
            if p.life > 0:
                alive.append(p)
        self.particles = alive
        for b in self.beads:
            b.life -= 1
        self.beads = [b for b in self.beads if b.life > 0]

    def draw(self, screen):
        L = self.light
        L.fill((0, 0, 0))
        scale = scale_at(self.head)
        drawn = min(OUTLINE_LEN, self.head)
        trail = [self.point(self.head - k) for k in range(drawn + 1)]  # trail[k] 是光头后方第 k 个点
        chunk = 5

        # 背景星点，缓慢闪烁
        for x, y, phase, rate, size, color in self.stars:
            k = 0.12 + 0.22 * (1 + math.sin(phase + self.frame * rate))
            pygame.draw.circle(L, scale_color(color, k), (x, y), size)

        # 粒子拖线，画在轮廓下面
        for p in self.particles:
            a = p.life / p.max_life
            pygame.draw.aaline(L, scale_color(lerp(p.color, WHITE, 0.35), a * 0.6), (p.ox, p.oy), (p.x, p.y))

        # 淡轮廓线：每个点停在它被画出时的大小，所以上一圈的大爱心会留在外面慢慢淡掉
        for k0 in range(drawn, 0, -chunk):
            pts = trail[max(k0 - chunk, 0):k0 + 1]
            a = OUTLINE_LEVEL * (1 - k0 / OUTLINE_LEN) ** 0.5
            pygame.draw.aalines(L, scale_color(OUTLINE, a), False, pts)

        # 当前轮廓内侧的闪烁小白点
        for x, y, phase, rate in self.sparkles:
            k = max(0.0, math.sin(phase + self.frame * rate))
            if k > 0.2:
                pygame.draw.circle(L, scale_color(WHITE, k), self.at(x, y, scale), 1 + (k > 0.85))

        # 光头后的加亮段：越旧越暗，靠近光头偏白、更粗
        for k0 in range(min(TRAIL_MAX, drawn), 0, -chunk):
            pts = trail[max(k0 - chunk, 0):k0 + 1]
            color = lerp(OUTLINE, WHITE, (1 - k0 / HEAD_LEN) ** 1.5) if k0 < HEAD_LEN else OUTLINE
            a = (1 - k0 / TRAIL_MAX) ** 0.8
            pygame.draw.lines(L, scale_color(color, a * 0.4), False, pts, 4 if k0 < HEAD_LEN else 3)
            pygame.draw.aalines(L, scale_color(color, a), False, pts)

        # 轮廓上的光珠：淡入淡出
        for b in self.beads:
            u = b.life / b.max_life
            k = min(1.0, (1 - u) * 6, u * 2.5)
            level = max(1, round(k * LEVELS))
            add_glow(L, scale_color(b.color, level / LEVELS), b.size * 3, b.x, b.y)
            pygame.draw.circle(L, scale_color(lerp(b.color, WHITE, 0.45), k), (b.x, b.y), b.size)

        # 射线末端：光斑 + 亮芯（圆点或十字星）
        for p in self.particles:
            a = p.life / p.max_life
            level = max(1, round(a * LEVELS))
            add_glow(L, scale_color(p.color, level / LEVELS * 0.7), p.size * 2, p.x, p.y)
            core = scale_color(lerp(p.color, WHITE, 0.6), a)
            if p.spark:
                d = p.size * 1.6
                pygame.draw.aaline(L, core, (p.x - d, p.y), (p.x + d, p.y))
                pygame.draw.aaline(L, core, (p.x, p.y - d), (p.x, p.y + d))
                pygame.draw.aaline(L, core, (p.x - d * 0.6, p.y - d * 0.6), (p.x + d * 0.6, p.y + d * 0.6))
                pygame.draw.aaline(L, core, (p.x - d * 0.6, p.y + d * 0.6), (p.x + d * 0.6, p.y - d * 0.6))
            else:
                pygame.draw.circle(L, core, (p.x, p.y), max(1, p.size * (0.4 + 0.6 * a)))

        # 光头
        hx, hy = trail[0]
        add_glow(L, scale_color(HOT_PINK, 0.5), 40, hx, hy)
        add_glow(L, scale_color(PINK, 0.8), 18, hx, hy)
        add_glow(L, WHITE, 8, hx, hy)

        L.blit(self.text, (0, 0), special_flags=pygame.BLEND_ADD)

        # 泛光：缩小再放大得到模糊图，叠加回去
        small = pygame.transform.smoothscale(L, (WIDTH // 4, HEIGHT // 4))
        tiny = pygame.transform.smoothscale(small, (WIDTH // 16, HEIGHT // 16))
        small.blit(pygame.transform.smoothscale(tiny, small.get_size()), (0, 0), special_flags=pygame.BLEND_ADD)
        bloom = pygame.transform.smoothscale(small, (WIDTH, HEIGHT))

        screen.blit(self.background, (0, 0))
        screen.blit(L, (0, 0), special_flags=pygame.BLEND_ADD)
        for _ in range(BLOOM_PASSES):
            screen.blit(bloom, (0, 0), special_flags=pygame.BLEND_ADD)
        screen.blit(self.vignette, (0, 0), special_flags=pygame.BLEND_MULT)


def main():
    if sys.platform == "win32":
        # 不让 Windows 按缩放比例放大窗口，否则 150% 缩放的屏幕上窗口会超出屏幕且发糊
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("love")
    clock = pygame.time.Clock()
    scene = Scene()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
        scene.step()
        scene.draw(screen)
        pygame.display.flip()
        clock.tick(FPS)
    pygame.quit()


if __name__ == "__main__":
    main()
