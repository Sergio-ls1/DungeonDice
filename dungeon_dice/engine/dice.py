import pygame
import random

class Dice:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 48, 48)
        self.value = 6
        self.rolling = False
        self.roll_time = 0
        self.last_switch = 0

    def roll(self):
        self.rolling = True
        self.roll_time = 0.5 # 0.5 segundos de animación de giro
        self.last_switch = 0

    def update(self, dt):
        if self.rolling:
            self.roll_time -= dt
            self.last_switch += dt
            if self.last_switch > 0.05:
                self.value = random.randint(1, 6)
                self.last_switch = 0
            if self.roll_time <= 0:
                self.rolling = False
                self.value = random.randint(1, 6)
                return self.value
        return None

    def draw(self, screen, font, bg_color=(240, 240, 240), border_color=(50, 50, 50), text_color=(0, 0, 0)):
        pygame.draw.rect(screen, bg_color, self.rect)
        pygame.draw.rect(screen, border_color, self.rect, 2)
        
        # Renderizamos el número del dado centrado
        text = font.render(str(self.value), True, text_color)
        tx = self.rect.x + (self.rect.width - text.get_width()) // 2
        ty = self.rect.y + (self.rect.height - text.get_height()) // 2
        screen.blit(text, (tx, ty))
