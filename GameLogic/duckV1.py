"""
Duck Hunt - ESP32-C6 BLE HID Edition
======================================
Requirements:
    pip install pygame

Run:
    python duck_hunt.py

Controls:
    - Move ESP32 (gyro) → moves the crosshair
    - Button press      → shoots (1 shot per press)
    - ESC               → quit
"""

import pygame
import sys
import random
import math
import time

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
WIN_W, WIN_H     = 1280, 720
FPS              = 60
MAX_DUCKS        = 3
STARTING_LIVES   = 6
STARTING_AMMO    = 10
GAME_DURATION    = 60          # seconds
DUCK_BASE_SPEED  = 180         # pixels per second (starting)
SPEED_INCREMENT  = 15          # added each time a duck is shot
MAX_SPEED        = 500

# Colors
SKY_TOP          = (102, 178, 255)
SKY_BOT          = (180, 225, 255)
GRASS_TOP        = (34,  139,  34)
GRASS_BOT        = (24,  100,  24)
CLOUD_COL        = (255, 255, 255)
DUCK_BODY        = (210, 140,  30)
DUCK_WING        = (180, 110,  10)
DUCK_BEAK        = (255, 180,   0)
DUCK_EYE         = (10,   10,  10)
DUCK_HIT_COL     = (255,  80,  80)
CROSSHAIR_COL    = (255,  50,  50)
CROSSHAIR_OUT    = (255, 255, 255)
TEXT_COL         = (255, 255, 255)
TEXT_SHADOW      = (0,    0,    0)
HUD_BG           = (0,    0,    0, 140)
MUZZLE_COL       = (255, 220,  80)
PANEL_BG         = (20,  20,   40, 200)

# ─────────────────────────────────────────────
#  HELPER: draw outlined text
# ─────────────────────────────────────────────
def draw_text(surf, text, font, x, y, color=TEXT_COL, shadow=TEXT_SHADOW, center=False):
    shadow_surf = font.render(text, True, shadow)
    text_surf   = font.render(text, True, color)
    if center:
        rect = text_surf.get_rect(center=(x, y))
        surf.blit(shadow_surf, (rect.x + 2, rect.y + 2))
        surf.blit(text_surf,   rect)
    else:
        surf.blit(shadow_surf, (x + 2, y + 2))
        surf.blit(text_surf,   (x, y))

# ─────────────────────────────────────────────
#  DUCK CLASS
# ─────────────────────────────────────────────
class Duck:
    FLAP_SPEED = 8   # frames per wing phase

    def __init__(self, speed):
        self.speed    = speed
        self.size     = 48
        self.reset(speed)

    def reset(self, speed):
        self.speed    = speed
        # Random direction
        self.dir      = random.choice([-1, 1])
        if self.dir == 1:
            self.x = -self.size
        else:
            self.x = WIN_W + self.size

        # Fly in the upper 60% of sky (avoid grass)
        self.y        = random.randint(60, int(WIN_H * 0.55))

        # Wavy path parameters
        self.wave_amp   = random.uniform(30, 90)
        self.wave_freq  = random.uniform(1.5, 3.5)
        self.base_y     = self.y
        self.time       = 0.0

        self.alive      = True
        self.hit        = False
        self.hit_timer  = 0
        self.flap_frame = 0
        self.wing_up    = True

    def update(self, dt, speed):
        if not self.alive:
            return
        self.speed  = speed
        self.time  += dt
        self.x     += self.dir * self.speed * dt
        self.y      = self.base_y + math.sin(self.time * self.wave_freq) * self.wave_amp

        self.flap_frame += 1
        if self.flap_frame >= self.FLAP_SPEED:
            self.flap_frame = 0
            self.wing_up = not self.wing_up

        if self.hit:
            self.hit_timer -= 1
            if self.hit_timer <= 0:
                self.alive = False

    def is_offscreen(self):
        return self.x < -self.size * 2 or self.x > WIN_W + self.size * 2

    def collides(self, px, py):
        # Generous hitbox
        hw = self.size * 0.9
        hh = self.size * 0.6
        return abs(px - self.x) < hw and abs(py - self.y) < hh

    def shoot(self):
        if not self.alive or self.hit:
            return False
        self.hit       = True
        self.hit_timer = 20   # frames before disappearing
        return True

    def draw(self, surf):
        if not self.alive:
            return
        x, y = int(self.x), int(self.y)
        s    = self.size
        col  = DUCK_HIT_COL if self.hit else DUCK_BODY
        wing = DUCK_HIT_COL if self.hit else DUCK_WING

        # Flip drawing direction
        flip = (self.dir == -1)

        # Body (ellipse)
        body_rect = pygame.Rect(x - s//2, y - s//3, s, int(s * 0.6))
        pygame.draw.ellipse(surf, col, body_rect)

        # Wing
        if self.wing_up:
            wing_pts = [
                (x - s//4 * (1 if not flip else -1), y - s//4),
                (x,                                   y - s//2),
                (x + s//4 * (1 if not flip else -1), y - s//4),
            ]
        else:
            wing_pts = [
                (x - s//4 * (1 if not flip else -1), y),
                (x,                                   y + s//3),
                (x + s//4 * (1 if not flip else -1), y),
            ]
        pygame.draw.polygon(surf, wing, wing_pts)

        # Head
        hx = x + (s // 3) * (self.dir)
        hy = y - s // 3
        pygame.draw.circle(surf, col, (hx, hy), s // 5)

        # Beak
        beak_dir = self.dir
        beak_pts = [
            (hx + int(s * 0.18) * beak_dir, hy),
            (hx + int(s * 0.38) * beak_dir, hy - 3),
            (hx + int(s * 0.38) * beak_dir, hy + 3),
        ]
        pygame.draw.polygon(surf, DUCK_BEAK, beak_pts)

        # Eye
        ex = hx + int(s * 0.08) * beak_dir
        pygame.draw.circle(surf, DUCK_EYE, (ex, hy - 2), 3)

# ─────────────────────────────────────────────
#  PARTICLE / MUZZLE FLASH
# ─────────────────────────────────────────────
class Particle:
    def __init__(self, x, y):
        angle  = random.uniform(0, math.pi * 2)
        speed  = random.uniform(80, 220)
        self.x = x
        self.y = y
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = random.uniform(0.15, 0.35)
        self.max_life = self.life
        self.color = random.choice([MUZZLE_COL, (255, 160, 30), (255, 80, 30)])
        self.r = random.randint(3, 7)

    def update(self, dt):
        self.x    += self.vx * dt
        self.y    += self.vy * dt
        self.vy   += 400 * dt   # gravity
        self.life -= dt

    def draw(self, surf):
        alpha = max(0, self.life / self.max_life)
        r = int(self.r * alpha)
        if r > 0:
            pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), r)

# ─────────────────────────────────────────────
#  CROSSHAIR DRAW
# ─────────────────────────────────────────────
def draw_crosshair(surf, x, y):
    size  = 22
    gap   = 6
    thick = 2

    for color, offset in [(CROSSHAIR_OUT, 2), (CROSSHAIR_COL, 0)]:
        # Horizontal lines
        pygame.draw.line(surf, color, (x - size, y + offset), (x - gap, y + offset), thick + (1 if offset else 0))
        pygame.draw.line(surf, color, (x + gap,  y + offset), (x + size, y + offset), thick + (1 if offset else 0))
        # Vertical lines
        pygame.draw.line(surf, color, (x + offset, y - size), (x + offset, y - gap), thick + (1 if offset else 0))
        pygame.draw.line(surf, color, (x + offset, y + gap),  (x + offset, y + size), thick + (1 if offset else 0))
        # Center dot
        pygame.draw.circle(surf, color, (x, y), 3 + (1 if offset else 0))

# ─────────────────────────────────────────────
#  BACKGROUND DRAW
# ─────────────────────────────────────────────
def draw_background(surf, clouds):
    # Sky gradient (manual bands)
    for i in range(WIN_H):
        t   = i / WIN_H
        r   = int(SKY_TOP[0] + (SKY_BOT[0] - SKY_TOP[0]) * t)
        g   = int(SKY_TOP[1] + (SKY_BOT[1] - SKY_TOP[1]) * t)
        b   = int(SKY_TOP[2] + (SKY_BOT[2] - SKY_TOP[2]) * t)
        pygame.draw.line(surf, (r, g, b), (0, i), (WIN_W, i))

    # Clouds
    for cx, cy, cr in clouds:
        for dx, dy, dr in [(-cr//2, 0, cr), (0, -cr//3, int(cr*0.75)), (cr//2, 0, int(cr*0.85))]:
            pygame.draw.circle(surf, CLOUD_COL, (int(cx + dx), int(cy + dy)), dr)

    # Grass
    grass_y = int(WIN_H * 0.72)
    for i in range(grass_y, WIN_H):
        t = (i - grass_y) / (WIN_H - grass_y)
        r = int(GRASS_TOP[0] + (GRASS_BOT[0] - GRASS_TOP[0]) * t)
        g = int(GRASS_TOP[1] + (GRASS_BOT[1] - GRASS_TOP[1]) * t)
        b = int(GRASS_TOP[2] + (GRASS_BOT[2] - GRASS_TOP[2]) * t)
        pygame.draw.line(surf, (r, g, b), (0, i), (WIN_W, i))

    # Grass edge detail
    grass_y2 = grass_y
    for gx in range(0, WIN_W, 18):
        h = random.randint(6, 16)
        pygame.draw.line(surf, (20, 120, 20), (gx, grass_y2), (gx + random.randint(-4,4), grass_y2 - h), 2)

# ─────────────────────────────────────────────
#  HUD DRAW
# ─────────────────────────────────────────────
def draw_hud(surf, score, lives, ammo, time_left, font_big, font_med, font_small):
    # Semi-transparent top bar
    bar = pygame.Surface((WIN_W, 52), pygame.SRCALPHA)
    bar.fill((0, 0, 0, 150))
    surf.blit(bar, (0, 0))

    # Score
    draw_text(surf, f"SCORE  {score:04d}", font_big, 20, 8, (255, 220, 60))

    # Timer
    tc = (255, 80, 80) if time_left < 10 else TEXT_COL
    draw_text(surf, f"TIME  {int(time_left):02d}s", font_big, WIN_W//2, 8, tc, center=False)

    # Lives (duck icons as ♥)
    lx = WIN_W - 260
    draw_text(surf, "LIVES", font_small, lx, 6, (200, 200, 200))
    for i in range(STARTING_LIVES):
        col = (255, 60, 60) if i < lives else (80, 80, 80)
        draw_text(surf, "♥", font_big, lx + 60 + i * 28, 6, col)

    # Ammo
    ax = 20
    draw_text(surf, "AMMO", font_small, ax, 38, (200, 200, 200))
    for i in range(STARTING_AMMO):
        col = (255, 200, 50) if i < ammo else (60, 60, 60)
        draw_text(surf, "•", font_med, ax + 55 + i * 22, 34, col)

# ─────────────────────────────────────────────
#  SCREEN: GAME OVER / WIN
# ─────────────────────────────────────────────
def draw_endscreen(surf, score, reason, font_huge, font_big, font_med):
    overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    surf.blit(overlay, (0, 0))

    draw_text(surf, reason,              font_huge, WIN_W//2, WIN_H//2 - 120, (255, 80, 80),  center=True)
    draw_text(surf, f"SCORE: {score}",   font_big,  WIN_W//2, WIN_H//2 - 30,  (255, 220, 60), center=True)
    draw_text(surf, "Press R to Restart or ESC to Quit", font_med, WIN_W//2, WIN_H//2 + 60, TEXT_COL, center=True)

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Duck Hunt — ESP32-C6 Edition")
    pygame.mouse.set_visible(False)
    pygame.event.set_grab(True)

    clock    = pygame.time.Clock()

    font_huge  = pygame.font.SysFont("impact",          72)
    font_big   = pygame.font.SysFont("impact",          32)
    font_med   = pygame.font.SysFont("couriernew",      24)
    font_small = pygame.font.SysFont("couriernew",      16)

    # Static clouds (x, y, radius)
    clouds = [(random.randint(80, WIN_W - 80),
               random.randint(60, 200),
               random.randint(40, 80)) for _ in range(6)]

    # Pre-render background (static, redraw each frame for grass blades randomness would flicker — bake it)
    bg = pygame.Surface((WIN_W, WIN_H))
    draw_background(bg, clouds)

    def new_game():
        return {
            "score":      0,
            "lives":      STARTING_LIVES,
            "ammo":       STARTING_AMMO,
            "time_left":  GAME_DURATION,
            "speed":      DUCK_BASE_SPEED,
            "ducks":      [Duck(DUCK_BASE_SPEED) for _ in range(MAX_DUCKS)],
            "particles":  [],
            "game_over":  False,
            "over_reason":"",
            "mx":         WIN_W // 2,
            "my":         WIN_H // 2,
            "prev_btn":   False,
        }

    state = new_game()

    while True:
        dt = clock.tick(FPS) / 1000.0

        # ── Events ───────────────────────────────
        shoot_this_frame = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key == pygame.K_r and state["game_over"]:
                    state = new_game()

            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1 and not state["game_over"]:
                    shoot_this_frame = True

        if state["game_over"]:
            screen.blit(bg, (0, 0))
            draw_endscreen(screen, state["score"], state["over_reason"],
                           font_huge, font_big, font_med)
            pygame.display.flip()
            continue

        # ── Mouse position (relative, captured) ──
        rel = pygame.mouse.get_rel()
        state["mx"] = max(0, min(WIN_W - 1, state["mx"] + rel[0]))
        state["my"] = max(0, min(WIN_H - 1, state["my"] + rel[1]))
        mx, my = state["mx"], state["my"]

        # ── Timer ────────────────────────────────
        state["time_left"] -= dt
        if state["time_left"] <= 0:
            state["time_left"] = 0
            state["game_over"]  = True
            state["over_reason"] = "TIME'S UP!"

        # ── Shoot ────────────────────────────────
        if shoot_this_frame and state["ammo"] > 0:
            state["ammo"] -= 1
            hit_any = False
            for duck in state["ducks"]:
                if duck.alive and not duck.hit and duck.collides(mx, my):
                    duck.shoot()
                    state["score"] += 100
                    state["speed"]  = min(state["speed"] + SPEED_INCREMENT, MAX_SPEED)
                    hit_any = True
                    # Particles at duck
                    for _ in range(18):
                        state["particles"].append(Particle(duck.x, duck.y))
                    break
            # Muzzle flash at crosshair regardless
            for _ in range(8):
                state["particles"].append(Particle(mx, my))
            if state["ammo"] == 0 and not hit_any:
                # Check if any ducks remain alive
                pass

        # Ammo out + no ducks to kill = game over (all ammo spent)
        if state["ammo"] == 0:
            alive_count = sum(1 for d in state["ducks"] if d.alive and not d.hit)
            if alive_count == MAX_DUCKS:
                # Out of ammo with all ducks alive
                state["game_over"]  = True
                state["over_reason"] = "OUT OF AMMO!"

        # ── Update ducks ─────────────────────────
        for i, duck in enumerate(state["ducks"]):
            duck.update(dt, state["speed"])

            if duck.is_offscreen() and not duck.hit:
                # Escaped — lose a life
                state["lives"] -= 1
                if state["lives"] <= 0:
                    state["lives"]      = 0
                    state["game_over"]   = True
                    state["over_reason"] = "GAME OVER!"
                duck.reset(state["speed"])

            elif not duck.alive:
                # Was shot and finished dying
                duck.reset(state["speed"])

        # ── Update particles ─────────────────────
        state["particles"] = [p for p in state["particles"] if p.life > 0]
        for p in state["particles"]:
            p.update(dt)

        # ── Draw ─────────────────────────────────
        screen.blit(bg, (0, 0))

        for duck in state["ducks"]:
            duck.draw(screen)

        for p in state["particles"]:
            p.draw(screen)

        draw_hud(screen, state["score"], state["lives"], state["ammo"],
                 state["time_left"], font_big, font_med, font_small)

        draw_crosshair(screen, mx, my)

        pygame.display.flip()

if __name__ == "__main__":
    main()