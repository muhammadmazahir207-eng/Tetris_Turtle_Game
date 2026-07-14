"""
TETRIS (turtle edition)
=========================

Classic Tetris built with Python's standard `turtle` module.

Controls:
  Left / Right   -> move piece
  Down           -> soft drop (move down one row, small score bonus)
  Up             -> rotate clockwise
  Space          -> hard drop (slam to the bottom instantly)
  P              -> pause / unpause
  Q / Escape     -> quit

Requirements:
  Python's built-in `turtle` module. On some Linux systems tkinter must be
  installed separately:
      sudo apt-get install python3-tk
"""

import turtle
import random
import sys

# ----------------------------------------------------------------------
# CONFIG / CONSTANTS
# ----------------------------------------------------------------------

COLS = 10
ROWS = 20
CELL = 24  # pixel size of one board cell

BOARD_WIDTH = COLS * CELL
BOARD_HEIGHT = ROWS * CELL

SIDE_PANEL_WIDTH = 200
SCREEN_WIDTH = BOARD_WIDTH + SIDE_PANEL_WIDTH + 60
SCREEN_HEIGHT = BOARD_HEIGHT + 80

# Board is centered-ish; BOARD_LEFT/BOARD_TOP define the pixel origin of
# the play field in turtle coordinates (0,0 = screen center).
BOARD_LEFT = -SCREEN_WIDTH // 2 + 40
BOARD_TOP = SCREEN_HEIGHT // 2 - 40

START_DROP_MS = 500
MIN_DROP_MS = 100
DROP_MS_PER_LEVEL = 40
LINES_PER_LEVEL = 10

LINE_SCORES = {1: 40, 2: 100, 3: 300, 4: 1200}
SOFT_DROP_BONUS = 1
HARD_DROP_BONUS = 2

COLOR_BG = "#101018"
COLOR_BOARD_BG = "#181828"
COLOR_GRID = "#2a2a3a"
COLOR_BORDER = "#e0e0e8"
COLOR_TEXT = "#f0f0f5"
COLOR_GHOST_OUTLINE = "#555566"

PIECE_COLORS = {
    "I": "#2ecfe0",
    "O": "#e8d92e",
    "T": "#a24fe0",
    "S": "#3fe05e",
    "Z": "#e0433f",
    "J": "#3f6fe0",
    "L": "#e0902e",
}

# Base shape of each tetromino inside a 4x4 box (x = col, y = row, both 0-3)
BASE_SHAPES = {
    "I": [(0, 1), (1, 1), (2, 1), (3, 1)],
    "O": [(1, 1), (2, 1), (1, 2), (2, 2)],
    "T": [(1, 1), (0, 2), (1, 2), (2, 2)],
    "S": [(1, 1), (2, 1), (0, 2), (1, 2)],
    "Z": [(0, 1), (1, 1), (1, 2), (2, 2)],
    "J": [(0, 1), (0, 2), (1, 2), (2, 2)],
    "L": [(2, 1), (0, 2), (1, 2), (2, 2)],
}


def rotate_cw(cells, box_size=4):
    """Rotate a set of (x, y) cells 90 degrees clockwise inside an
    box_size x box_size bounding box."""
    return [(box_size - 1 - y, x) for (x, y) in cells]


def build_rotation_states():
    """Precompute the 4 rotation states for every piece type."""
    states = {}
    for ptype, base in BASE_SHAPES.items():
        rotations = [base]
        current = base
        for _ in range(3):
            current = rotate_cw(current)
            rotations.append(current)
        states[ptype] = rotations
    return states


ROTATION_STATES = build_rotation_states()


# ----------------------------------------------------------------------
# BAG RANDOMIZER (standard "7-bag" so pieces feel fair, not fully random)
# ----------------------------------------------------------------------

class Bag:
    def __init__(self):
        self.pieces = []

    def next(self):
        if not self.pieces:
            self.pieces = list(BASE_SHAPES.keys())
            random.shuffle(self.pieces)
        return self.pieces.pop()


# ----------------------------------------------------------------------
# PIECE
# ----------------------------------------------------------------------

class Piece:
    def __init__(self, ptype, col, row):
        self.type = ptype
        self.rotation = 0
        self.col = col
        self.row = row

    def cells(self, rotation=None, col=None, row=None):
        """Absolute board (col, row) coordinates for this piece."""
        rotation = self.rotation if rotation is None else rotation
        col = self.col if col is None else col
        row = self.row if row is None else row
        shape = ROTATION_STATES[self.type][rotation % 4]
        return [(col + x, row + y) for (x, y) in shape]


# ----------------------------------------------------------------------
# BOARD
# ----------------------------------------------------------------------

class Board:
    def __init__(self, cols, rows):
        self.cols = cols
        self.rows = rows
        self.grid = [[None for _ in range(cols)] for _ in range(rows)]

    def is_valid(self, cells):
        for (c, r) in cells:
            if c < 0 or c >= self.cols:
                return False
            if r >= self.rows:
                return False
            if r >= 0 and self.grid[r][c] is not None:
                return False
        return True

    def lock_piece(self, piece):
        color = PIECE_COLORS[piece.type]
        for (c, r) in piece.cells():
            if r >= 0:
                self.grid[r][c] = color

    def clear_lines(self):
        full_rows = [r for r in range(self.rows) if all(cell is not None for cell in self.grid[r])]
        if not full_rows:
            return 0
        for r in full_rows:
            del self.grid[r]
            self.grid.insert(0, [None for _ in range(self.cols)])
        return len(full_rows)


# ----------------------------------------------------------------------
# GAME
# ----------------------------------------------------------------------

class Game:
    def __init__(self):
        self.screen = turtle.Screen()
        self.screen.setup(width=SCREEN_WIDTH, height=SCREEN_HEIGHT)
        self.screen.bgcolor(COLOR_BG)
        self.screen.title("Tetris")
        self.screen.tracer(0)

        self.board = Board(COLS, ROWS)
        self.bag = Bag()

        self.current = None
        self.next_type = self.bag.next()
        self.spawn_piece()

        self.score = 0
        self.lines_cleared = 0
        self.level = 1
        self.drop_ms = START_DROP_MS

        self.paused = False
        self.game_over = False
        self.running = True

        self._make_pens()
        self._draw_static_frame()
        self._bind_keys()

    # ---------------- setup ----------------

    def _make_pens(self):
        # one reusable stamping turtle for board + piece blocks
        self.block_pen = turtle.Turtle()
        self.block_pen.hideturtle()
        self.block_pen.penup()
        self.block_pen.shape("square")
        self.block_pen.shapesize(stretch_wid=CELL / 20, stretch_len=CELL / 20)

        # static frame lines (board border, panel divider) drawn once
        self.frame_pen = turtle.Turtle()
        self.frame_pen.hideturtle()
        self.frame_pen.penup()
        self.frame_pen.color(COLOR_BORDER)

        # HUD text
        self.hud = turtle.Turtle()
        self.hud.hideturtle()
        self.hud.penup()
        self.hud.color(COLOR_TEXT)

        # big centered message (pause / game over)
        self.msg = turtle.Turtle()
        self.msg.hideturtle()
        self.msg.penup()
        self.msg.color(COLOR_TEXT)

    def _draw_static_frame(self):
        pen = self.frame_pen
        pen.pensize(3)
        pen.goto(BOARD_LEFT, BOARD_TOP)
        pen.pendown()
        pen.goto(BOARD_LEFT + BOARD_WIDTH, BOARD_TOP)
        pen.goto(BOARD_LEFT + BOARD_WIDTH, BOARD_TOP - BOARD_HEIGHT)
        pen.goto(BOARD_LEFT, BOARD_TOP - BOARD_HEIGHT)
        pen.goto(BOARD_LEFT, BOARD_TOP)
        pen.penup()

        # faint grid lines inside the board
        pen.color(COLOR_GRID)
        pen.pensize(1)
        for c in range(1, COLS):
            x = BOARD_LEFT + c * CELL
            pen.goto(x, BOARD_TOP)
            pen.pendown()
            pen.goto(x, BOARD_TOP - BOARD_HEIGHT)
            pen.penup()
        for r in range(1, ROWS):
            y = BOARD_TOP - r * CELL
            pen.goto(BOARD_LEFT, y)
            pen.pendown()
            pen.goto(BOARD_LEFT + BOARD_WIDTH, y)
            pen.penup()
        pen.color(COLOR_BORDER)

    def _bind_keys(self):
        s = self.screen
        s.onkeypress(self.move_left, "Left")
        s.onkeypress(self.move_right, "Right")
        s.onkeypress(self.soft_drop, "Down")
        s.onkeypress(self.rotate_piece, "Up")
        s.onkeypress(self.hard_drop, "space")
        s.onkeypress(self.toggle_pause, "p")
        s.onkeypress(self.quit_game, "q")
        s.onkeypress(self.quit_game, "Escape")
        s.listen()

    # ---------------- piece spawning ----------------

    def spawn_piece(self):
        ptype = self.next_type
        self.next_type = self.bag.next()
        col = COLS // 2 - 2
        row = -1
        self.current = Piece(ptype, col, row)

        if not self.board.is_valid(self.current.cells()):
            self.game_over = True

    # ---------------- piece movement ----------------

    def move_left(self):
        if self.paused or self.game_over:
            return
        cells = self.current.cells(col=self.current.col - 1)
        if self.board.is_valid(cells):
            self.current.col -= 1

    def move_right(self):
        if self.paused or self.game_over:
            return
        cells = self.current.cells(col=self.current.col + 1)
        if self.board.is_valid(cells):
            self.current.col += 1

    def soft_drop(self):
        if self.paused or self.game_over:
            return
        if self._try_drop_one():
            self.score += SOFT_DROP_BONUS

    def hard_drop(self):
        if self.paused or self.game_over:
            return
        dropped = 0
        while self._try_drop_one():
            dropped += 1
        self.score += dropped * HARD_DROP_BONUS
        self._lock_and_advance()

    def rotate_piece(self):
        if self.paused or self.game_over:
            return
        new_rotation = (self.current.rotation + 1) % 4
        # try the rotation as-is, then simple wall kicks left/right
        for kick in (0, -1, 1, -2, 2):
            cells = self.current.cells(rotation=new_rotation, col=self.current.col + kick)
            if self.board.is_valid(cells):
                self.current.rotation = new_rotation
                self.current.col += kick
                return
        # no valid rotation found; do nothing

    def _try_drop_one(self):
        """Attempt to move the current piece down by one row.
        Returns True if it moved, False if it's blocked (should lock)."""
        cells = self.current.cells(row=self.current.row + 1)
        if self.board.is_valid(cells):
            self.current.row += 1
            return True
        return False

    def _lock_and_advance(self):
        self.board.lock_piece(self.current)
        cleared = self.board.clear_lines()
        if cleared:
            self.lines_cleared += cleared
            self.score += LINE_SCORES.get(cleared, 0) * self.level
            new_level = self.lines_cleared // LINES_PER_LEVEL + 1
            if new_level != self.level:
                self.level = new_level
                self.drop_ms = max(MIN_DROP_MS, START_DROP_MS - (self.level - 1) * DROP_MS_PER_LEVEL)
        self.spawn_piece()

    # ---------------- control ----------------

    def toggle_pause(self):
        if self.game_over:
            return
        self.paused = not self.paused

    def quit_game(self):
        self.running = False

    # ---------------- rendering ----------------

    def draw_board_and_piece(self):
        self.block_pen.clearstamps()

        for r in range(ROWS):
            for c in range(COLS):
                color = self.board.grid[r][c]
                if color:
                    self._stamp_cell(c, r, color)

        if not self.game_over:
            color = PIECE_COLORS[self.current.type]
            for (c, r) in self.current.cells():
                if r >= 0:
                    self._stamp_cell(c, r, color)

        self._draw_next_preview()

    def _stamp_cell(self, col, row, color):
        x = BOARD_LEFT + col * CELL + CELL / 2
        y = BOARD_TOP - row * CELL - CELL / 2
        self.block_pen.goto(x, y)
        self.block_pen.color(color)
        self.block_pen.stamp()

    def _draw_next_preview(self):
        panel_x = BOARD_LEFT + BOARD_WIDTH + 50
        panel_top = BOARD_TOP - 40
        shape = ROTATION_STATES[self.next_type][0]
        color = PIECE_COLORS[self.next_type]
        for (x, y) in shape:
            px = panel_x + x * CELL
            py = panel_top - y * CELL
            self.block_pen.goto(px, py)
            self.block_pen.color(color)
            self.block_pen.stamp()

    def draw_hud(self):
        self.hud.clear()
        panel_x = BOARD_LEFT + BOARD_WIDTH + 50

        self.hud.goto(panel_x, BOARD_TOP + 10)
        self.hud.write("NEXT", font=("Arial", 14, "bold"))

        self.hud.goto(panel_x, BOARD_TOP - 130)
        self.hud.write(f"SCORE\n{self.score}", font=("Arial", 14, "bold"))

        self.hud.goto(panel_x, BOARD_TOP - 190)
        self.hud.write(f"LEVEL\n{self.level}", font=("Arial", 14, "bold"))

        self.hud.goto(panel_x, BOARD_TOP - 250)
        self.hud.write(f"LINES\n{self.lines_cleared}", font=("Arial", 14, "bold"))

        self.hud.goto(panel_x, BOARD_TOP - 340)
        self.hud.write("Left/Right: move\nDown: soft drop\nUp: rotate\nSpace: hard drop\n"
                        "P: pause\nQ: quit", font=("Arial", 10, "normal"))

        self.msg.clear()
        if self.game_over:
            self.msg.goto(BOARD_LEFT + BOARD_WIDTH / 2, 0)
            self.msg.write("GAME OVER", align="center", font=("Arial", 26, "bold"))
        elif self.paused:
            self.msg.goto(BOARD_LEFT + BOARD_WIDTH / 2, 0)
            self.msg.write("PAUSED", align="center", font=("Arial", 26, "bold"))

    # ---------------- main loop ----------------

    def game_loop(self):
        if not self.running:
            self.screen.bye()
            return

        if not self.paused and not self.game_over:
            if not self._try_drop_one():
                self._lock_and_advance()

        self.draw_board_and_piece()
        self.draw_hud()
        self.screen.update()

        self.screen.ontimer(self.game_loop, self.drop_ms)

    def run(self):
        self.game_loop()
        self.screen.mainloop()


# ----------------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------------

if __name__ == "__main__":
    game = Game()
    game.run()
