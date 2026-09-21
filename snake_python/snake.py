"""Simple Snake game using tkinter. Arrow keys / WASD to move, R to restart."""
import random
import tkinter as tk

CELL = 20
COLS, ROWS = 24, 20
DELAY_MS = 110


class Snake:
    def __init__(self, root):
        self.root = root
        root.title("Snake")
        self.canvas = tk.Canvas(root, width=COLS * CELL, height=ROWS * CELL, bg="#111")
        self.canvas.pack()
        root.bind("<Key>", self.on_key)
        self.reset()
        self.tick()

    def reset(self):
        self.snake = [(COLS // 2, ROWS // 2), (COLS // 2 - 1, ROWS // 2)]
        self.direction = (1, 0)
        self.pending = self.direction
        self.score = 0
        self.alive = True
        self.place_food()

    def place_food(self):
        free = [(x, y) for x in range(COLS) for y in range(ROWS) if (x, y) not in self.snake]
        self.food = random.choice(free) if free else None

    def on_key(self, event):
        keys = {"Up": (0, -1), "w": (0, -1), "Down": (0, 1), "s": (0, 1),
                "Left": (-1, 0), "a": (-1, 0), "Right": (1, 0), "d": (1, 0)}
        if event.keysym in ("r", "R"):
            self.reset()
        elif event.keysym in keys:
            d = keys[event.keysym]
            if (d[0] + self.direction[0], d[1] + self.direction[1]) != (0, 0):
                self.pending = d

    def tick(self):
        if self.alive:
            self.step()
        self.draw()
        self.root.after(DELAY_MS, self.tick)

    def step(self):
        self.direction = self.pending
        x, y = self.snake[0]
        head = (x + self.direction[0], y + self.direction[1])
        eating = head == self.food
        body = self.snake if eating else self.snake[:-1]
        if not (0 <= head[0] < COLS and 0 <= head[1] < ROWS) or head in body:
            self.alive = False
            return
        self.snake.insert(0, head)
        if eating:
            self.score += 1
            self.place_food()
        else:
            self.snake.pop()

    def draw(self):
        c = self.canvas
        c.delete("all")
        if self.food:
            fx, fy = self.food
            c.create_oval(fx * CELL + 2, fy * CELL + 2, (fx + 1) * CELL - 2, (fy + 1) * CELL - 2, fill="#e33")
        for i, (x, y) in enumerate(self.snake):
            c.create_rectangle(x * CELL + 1, y * CELL + 1, (x + 1) * CELL - 1, (y + 1) * CELL - 1,
                               fill="#6f6" if i == 0 else "#3a3", outline="")
        c.create_text(6, 6, anchor="nw", fill="white", text=f"Score: {self.score}")
        if not self.alive:
            c.create_text(COLS * CELL // 2, ROWS * CELL // 2, fill="white", font=("Arial", 16),
                          text="Game over - press R to restart")


if __name__ == "__main__":
    root = tk.Tk()
    Snake(root)
    root.mainloop()
