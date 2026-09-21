// Simple console Snake for Windows. WASD / arrow keys to move, Q to quit.
// Build: g++ snake.cpp -o snake.exe    (or: cl snake.cpp)
#include <conio.h>
#include <windows.h>

#include <cstdlib>
#include <ctime>
#include <deque>
#include <iostream>
#include <string>

const int W = 30, H = 16;

struct Pt { int x, y; };

static bool onSnake(const std::deque<Pt>& s, Pt p) {
    for (const Pt& q : s) if (q.x == p.x && q.y == p.y) return true;
    return false;
}

static Pt newFood(const std::deque<Pt>& s) {
    Pt f;
    do { f = {rand() % W, rand() % H}; } while (onSnake(s, f));
    return f;
}

static void draw(const std::deque<Pt>& s, Pt food, int score) {
    std::string out = "Score: " + std::to_string(score) + "   (WASD/arrows, Q quits)\n";
    out += std::string(W + 2, '#') + "\n";
    for (int y = 0; y < H; y++) {
        out += '#';
        for (int x = 0; x < W; x++) {
            if (x == s.front().x && y == s.front().y) out += 'O';
            else if (onSnake(s, {x, y})) out += 'o';
            else if (x == food.x && y == food.y) out += '*';
            else out += ' ';
        }
        out += "#\n";
    }
    out += std::string(W + 2, '#') + "\n";
    COORD home = {0, 0};
    SetConsoleCursorPosition(GetStdHandle(STD_OUTPUT_HANDLE), home);
    std::cout << out << std::flush;
}

int main() {
    srand((unsigned)time(nullptr));
    system("cls");
    std::deque<Pt> snake = {{W / 2, H / 2}, {W / 2 - 1, H / 2}};
    Pt dir = {1, 0}, food = newFood(snake);
    int score = 0;

    while (true) {
        while (_kbhit()) {
            int c = _getch();
            Pt d = dir;
            if (c == 0 || c == 224) {  // arrow keys arrive as two codes
                switch (_getch()) {
                    case 72: d = {0, -1}; break;
                    case 80: d = {0, 1}; break;
                    case 75: d = {-1, 0}; break;
                    case 77: d = {1, 0}; break;
                }
            } else {
                switch (tolower(c)) {
                    case 'w': d = {0, -1}; break;
                    case 's': d = {0, 1}; break;
                    case 'a': d = {-1, 0}; break;
                    case 'd': d = {1, 0}; break;
                    case 'q': return 0;
                }
            }
            if (d.x + dir.x != 0 || d.y + dir.y != 0) dir = d;
        }

        Pt head = {snake.front().x + dir.x, snake.front().y + dir.y};
        bool eating = head.x == food.x && head.y == food.y;
        if (!eating) snake.pop_back();
        if (head.x < 0 || head.x >= W || head.y < 0 || head.y >= H || onSnake(snake, head)) break;
        snake.push_front(head);
        if (eating) {
            score++;
            food = newFood(snake);
        }
        draw(snake, food, score);
        Sleep(120);
    }
    std::cout << "\nGame over! Final score: " << score << "\n";
    return 0;
}
