# cint primer: what `cintc` compiles, written to be read once

Status: guide, public edition 1, 2026-11-11. Checked on cint 0.2.18 (compiler source identity
`baa6d80a6614ba2872e763cb45e5f80a45995578cd3288fc369b0525bb2f661f`). It states what `cintc`, the compiler of
the `cint` command, compiles and runs; SPEC-04P.5 states the language, and where the two differ this page says
so. Every example here is compiled or run by `python check_primer.py --cint PATH`, in the repository of this
server, so a block that stops holding fails that check. The reader knows C or Python.

## 1. The short list

1. No implicit conversion, widening included: `b + (a as I64)`. `as` is checked and faults `E_NARROW`; `as%`
   wraps, `as|` saturates.
2. `+ - * / %` and `<<` are checked and fault. `+% -% *%` wrap and `+| -| *|` saturate. `/` and `%` floor:
   `-7 / 2` is `-4`. Use `div_trunc` and `rem_trunc` for C's result.
3. A literal takes its type from context and must fit it. An index, a range bound and a loop variable are
   `I64`: `a[k as I64]`.
4. Conditions are `Bool` (`if (n != 0)`), braces are required, comparisons do not chain, and `&&` with `||`
   needs parentheses.
5. A string statement prints: `"x={x}\n";`. No newline is added. `{{` and `}}` print braces.
6. A call whose result is not `void` is used or dropped with `_ =`. Parameters are read-only: copy one to a
   local to change it.
7. Every scalar has an initializer. Arrays and structs without one are zero.
8. A name is declared once in view: no shadowing, and no keyword or built-in name (section 6): `by`, `in`,
   `out`, `over`, `type`, `test`, `count`, `len`, `size`, `min`, `max`, `copy`, `fill`, `sum`, `abs`.
9. Text is bytes: `in U8[_]` views and `b"..."`. `Str` values, `enum`, tuples, `for x in xs`, `do`, `type`,
   `const` arrays and the other forms of section 4 are C9102 in `cintc`.
10. A module-level variable is not passed to a function that writes it (C5012): pass a copy.
11. Errors are values (`E!T`, `try`, `catch`). Faults stop the run and cannot be caught.
12. A file with a function has its statements in `void main() { ... }`. A top-level statement makes the file
    a script, whose variables no function sees (C3004).
13. The commands are `cint run`, `cint test`, `cint build` and `cint emit-c`. There is no `cint check`: a
    compile check is `cint emit-c --root . --out DIR FILE.ci`, or the MCP tool `cint_check`.
14. A diagnostic often prints its category. Look the code up in section 5, or with `cint_lookup_diagnostic`.

## 2. Getting and running `cint`

```sh
git clone https://github.com/pennyleans/cint-public-build.git
cd cint-public-build
python3 tools/cint_bootstrap.py --leg gcc     # or clang, msvc, apple-clang; a few minutes
<build>/boot/gcc/cint --version               # cint 0.2.18, the compiler source identity, the runtime contract
```

Python 3 and a C17 compiler are required. `<build>` is `CINT_BUILD`, or `cint-build` in the system temporary
directory. The tools of this server find that `cint` on `PATH`, by `CINT_PATH`, or under `<build>/boot`.

| command | does |
| --- | --- |
| `cint run FILE.ci [-- ARG...]` | compiles and runs `main` or a script; keeps the executable in the run cache, so a second run does not compile; `--rebuild` compiles again |
| `cint test [FILE.ci \| DIR]` | runs the `test` blocks, each from fresh module state |
| `cint build [--out DIR] [--app] [--lib] [--frame-arena N] FILE.ci` | writes the executable (`built: DIR/NAME`); `--app` makes every word of its command line a program argument; `--lib` builds a library for a host program |
| `cint emit-c --root DIR --out DIR FILE.ci` | writes the generated C and runs nothing: the compile check |
| `cint --json ...` | one JSON object a line on stderr: `CINT-DIAG-1`, `CINT-FAULT-1`, `CINT-TEST-1` |

| exit status | meaning |
| --- | --- |
| 0 | completed |
| 1 | runtime fault; stdout holds what was printed before it |
| 2 | compile error; nothing ran |
| 3 | a test failed |
| 4 | usage error, an extern with no host function included |
| 5 | environment failure: no C compiler, unreadable input |
| 6 | `main` returned an error value |
| 7 | internal error |

The cache is `--cache DIR`, else `CINT_CACHE`, else the platform's cache directory. On Windows `cint` takes
relative input paths only. `cint run` and `cint test` supply the service externs (`console`, `fs`) and no
others, so a module that declares its own `extern` builds with `cint build --lib` for a host program and does
not start under `cint run` (exit status 4).

## 3. The language by example

### 3.1 A program

```ci run
// A program is one `main`. Definitions come in any order; there are no prototypes.
const I64 LIMIT = 5;

I64 square(I64 x) {
    return x * x;
}

void main() {
    I64 total = 0;
    for i in 0..LIMIT {
        total += square(i);
    }
    "total={total}\n";
    if (total > 20 && total < 40) {
        "in range\n";
    } else {
        "out of range\n";
    }
}
```

```output
total=30
in range
```

### 3.2 Integers

The types are `I8` to `I64`, `U8` to `U64`, `I128` to `I1024`, and `Bool`, which is not an integer.

```ci run
void main() {
    I32 small = 300;
    I64 wide = small as I64;          // no implicit conversion, widening included
    U8 low = wide as% U8;             // wraps: 300 mod 256
    U8 top = wide as| U8;             // saturates
    U8 safe = wide as? U8 catch 0;    // an error value in place of the fault
    "{wide} {low} {top} {safe}\n";

    "{-7 / 2} {-7 % 2} {div_trunc(-7, 2)} {rem_trunc(-7, 2)}\n";      // / and % floor
    "{div_round(7, 2, half_even)} {muldiv(I64, 10, 20, 3, floor)} {isqrt(17)}\n";

    U8 a = 250;
    U8 b = a +% 10;                   // wrapping add
    U8 c = a +| 10;                   // saturating add
    I64 seed = 1;
    seed = seed *% 6364136223846793005 +% 1442695040888963407;      // a hash step wraps on purpose
    "{b} {c} {seed}\n";

    U32 w = 0x1234_5678;
    U32 low_byte = w & 0xFF;          // bitwise operators bind tighter than comparisons
    "{low_byte:#x} {w >> 24:#x} {rotl(w, 8):#x} {(w & 0xFF) == 0x78}\n";
    "{I64.max} {I8.min} {min(3, 4)} {abs(-3)} {clamp(9, 0, 5)}\n";
}
```

```output
300 44 255 0
-4 1 -3 -1
4 66 4
4 255 7806831264735756412
0x78 0x12 0x34567812 true
9223372036854775807 -128 3 3 5
```

A checked operation that has no answer in its type stops the run with a fault record on stderr:

```ci fault E_OVERFLOW
void main() {
    I64 big = I64.max;
    "before\n";
    I64 next = big + 1;
    "never printed {next}\n";
}
```

```output
before
```

### 3.3 Fixed point and wide integers

There is no floating point. `Q<i>.<f>` is signed fixed point with `i + f` of 8, 16, 32, 64 or 128 bits.

```ci run
void main() {
    Q32.32 a = 1.5;
    Q32.32 b = 0.25;
    Q32.32 c = a * b + a / b;               // * and / round half to even
    Q16.16 tenth = 0.1 round half_even;     // 0.1 is not on the grid, so the literal says how to round
    I64 whole = c as I64;                   // rounds half to even, then checks the range
    "{c} {whole} {mul(a, b, floor)} {tenth!raw} {c:.2}\n";

    I64 big = I64.max;
    I128 product = (big as I128) * (big as I128);
    I256 huge = 1;
    for i in 0..200 { huge *= 2; }
    "{product}\n{huge}\n";
}
```

```output
6.375 6 0.375 6554 6.38
85070591730234615847396907784232501249
1606938044258990275541962092341162602522202993782792835301376
```

### 3.4 Arrays, slices and views

```ci run
I64 total[n](in I64[n] xs) {           // n is bound from the argument's extent
    I64 t = 0;
    for i in 0..n { t += xs[i]; }
    return t;
}

void scale(inout I64[_] xs, I64 k) {   // _ takes any extent; writes through inout reach the caller
    for i in 0..len(xs) { xs[i] *= k; }
}

void main() {
    I64[5] xs = [1, 2, 3, 4, 5];       // with no initializer, zeros
    scale(xs[1..4], 10);               // a slice is a view of the same storage
    "{total(xs)} {sum(xs)} {max(xs)} {xs}\n";      // a call of your own function goes before an array hole

    in I64[_] head = xs[0..2];         // a read-only view variable
    inout I64[_] tail = xs[3..];       // a writable one
    tail[0] = 7;
    "{head[1]} {xs[3]} {len(tail)} {sum(xs[0..5 by 2])}\n";

    I64[5] ys = xs;                    // an owned copy; ys = xs; and copy(ys, xs) copy too
    ys[0] = 99;
    I32[2, 3] grid;                    // rank 2, row-major
    grid[1, 2] = 60;
    "{xs[0]} {ys[0]} {grid[1, 2]} {extent(grid, 1)} {size(grid)} {equal(xs, ys)}\n";
}
```

```output
96 96 40 [1, 20, 30, 40, 5]
20 7 2 36
1 99 60 3 6 false
```

Every index is checked. A negative index does not count from the end:

```ci fault E_BOUNDS
void main() {
    I64[3] a = [1, 2, 3];
    I64 i = -1;
    "{a[i]}\n";
}
```

A local array lives in the frame arena, 2,097,152 elements by default, whatever the element type. A larger
one faults `E_BOUNDS` (`arena.alloc`) at its declaration: run with `cint run --frame-arena N FILE.ci`, or
build with `cint build --frame-arena N`. A local array costs no bytes of the executable; a module-level array
does, and holds at most 65,536 elements (section 4).

### 3.5 Bytes and text

Text is bytes. `b"..."` is a read-only `U8` view of static storage, and a character literal is its code
point. `Str` values are not compiled (section 4), so a function that takes text takes `in U8[_]`.

```ci run
error ParseError { empty, bad_digit }

ParseError!I64 parse_u(in U8[_] s) {
    if (len(s) == 0) { return .empty; }
    I64 v = 0;
    for i in 0..len(s) {
        if (s[i] < '0' || s[i] > '9') { return .bad_digit; }
        v = v * 10 + ((s[i] - '0') as I64);
    }
    return v;
}

void main() {
    U8[5] word = b"hello";             // the extent equals the literal's length
    in U8[_] rest = b"world";
    Bool same = equal(word[0..2], b"he");
    I64 n = parse_u(b"1234") catch -1;
    I64 bad = parse_u(b"12x4") catch -1;
    U8 brace = b"{{"[0];               // braces are doubled in every literal
    "{word[0]} {len(rest)} {same} {n} {bad} {brace}\n";
}
```

```output
104 5 true 1234 -1 123
```

A hole holds no string literal (C1035), so a call that takes `b"..."` is made before the print statement, as
`same` is above. Bytes are written as text with `console.write` (section 3.12).

### 3.6 Structs

```ci run
struct Entry {
    I64 kind;
    I64 cents;
}

struct Acc { I64 n; I64 total; }

void add(inout Acc a, I64 v) {
    a.n += 1;
    a.total += v;
}

Entry make(I64 cents) {
    return Entry(kind = 1, cents = cents);     // by name, or in order: Entry(1, cents)
}

I64 cents_of[n](in Entry[n] book, I64 i) {     // a struct array takes a size parameter (section 4)
    return book[i].cents;
}

void main() {
    Entry[3] book;                             // zero-filled
    book[0] = make(125);
    book[1].cents = 40;
    Acc acc;
    for i in 0..3 { add(acc, cents_of(book, i)); }
    "{acc.n} {acc.total} {book[0].kind}\n";
}
```

```output
3 165 1
```

Assignment copies a struct. Compare structs field by field: `==` on two struct values is C2103 in SPEC-04P.5
(6.3, LS-313), and in cint 0.2.18 it ends `cintc` with an internal error (exit status 7).

### 3.7 Errors and faults

An error is a value for an outcome the caller handles. A fault is a broken contract (overflow, bounds, a
failed `assert`): it stops the run, and no code catches it.

```ci run
error LedgerError { overdrawn, closed }

LedgerError!I64 withdraw(I64 balance, I64 amount) {
    if (amount > balance) { return .overdrawn; }
    return balance - amount;
}

LedgerError!void settle(I64 balance) {
    I64 left = try withdraw(balance, 30);          // try passes the error to the caller
    "left {left}\n";
    return;
}

I64 code_of(I64 balance) {
    I64 left = withdraw(balance, 30) catch (e) {   // the block leaves: return, break or continue
        if (e == .overdrawn) { return -1; }
        return -2;
    };
    return left;
}

void main() {
    I64 a = withdraw(100, 30) catch 0;             // a value in place of any error
    _ = withdraw(1, 2);                            // the one way to drop a result and its error
    settle(5) catch (e) { "settle failed\n"; };    // the statement form, for an E!void call
    "{a} {code_of(100)} {code_of(5)}\n";
}
```

```output
settle failed
70 70 -1
```

An error union is a function result only, consumed at the call by `try`, `catch` or `_ =`. A value of an
error set is an ordinary value: `LedgerError last = .closed;`, compared with `==`, or the scrutinee of a
`switch` that lists every value. `LedgerError!void main()` may return an error; `cint run` then exits 6 and
prints `error: MODULE.LedgerError.overdrawn (tag 1)`.

### 3.8 Control flow

```ci run
void main() {
    for i in 0..3 { "{i} "; }                      // half-open
    for i in 1..=3 { "{i} "; }                     // inclusive
    for (I64 i = 10; i > 0; i -= 4) { "{i} "; }    // the C form, for any other step
    "\n";

    I64 n = 0;
    rows: for i in 0..5 {
        for j in 0..5 {
            if (j == 2) { continue rows; }
            if (i == 3) { break rows; }
            n += 1;
        }
    }
    while (n > 4) { n -= 1; }
    I64 side = n > 0 ? 1 : -1;
    "{n} {side}\n";

    switch (n) {
        case 0:
            "zero\n";
        case 1..=4, 9:                             // case ranges are inclusive; nothing falls through
            "small\n";
            fallthrough;                           // unless it is written
        case 5:
            "five or small\n";
        default:
            "other\n";
    }
    defer { "last\n"; }                            // runs when the block exits; not after a fault
    "first\n";
}
```

```output
0 1 2 1 2 3 10 6 2 
4 1
small
five or small
first
last
```

The loop variable of a range `for` is read-only. `i++;` and `i--;` are statements, never expressions. A
`switch` has `default` or covers every value. A function with a result needs a `return` after a
`while (true)` loop (C4001).

### 3.9 Printing

```ci run
void main() {
    I64 n = 1234567;
    "{n} {n:_} {n:,} {n:x} {n:#X} {n:b}\n";
    "[{n:>10}] [{n:<10}] [{n:^11}] [{n:010}] [{n:+}]\n";
    "{n=} {n:/100} {n + 1} {(n > 0 ? 1 : 0)}\n";     // {x=} prints the text and the value; /100 is exact
    Bool ok = true;
    I64[3] xs = [1, -2, 3];
    Q32.32 q = 0.125;
    "{ok} {xs} {xs:+} {q} {q:.2} {q!raw} {{braces}}\n";
}
```

```output
1234567 1_234_567 1,234,567 12d687 0x12D687 100101101011010000111
[   1234567] [1234567   ] [  1234567  ] [0001234567] [+1234567]
n=1234567 12345.67 1234568 1
true [1, -2, 3] [+1, -2, +3] 0.125 0.12 536870912 {braces}
```

Holes are allowed in print statements and `assert` messages only. A conditional expression in a hole takes
parentheses. Output is the same bytes on every platform; `cint` itself writes only to stderr.

### 3.10 Modules and state

One file is one module, named by its path from the source root. `export` makes a declaration visible to
importers. A module-level variable has a constant initializer or none.

```ci module geo/vec.ci
export const I64 SCALE = 10;
export struct V3 { I64 x; I64 y; I64 z; }
export I64 dot3(V3 a, V3 b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}
```

```ci module tab.ci
I64[8] cells;                      // private module state, zero-filled
export I64 writes = 0;
export void put(I64 i, I64 v) {
    cells[i] = v;
    writes += 1;
}
export I64 get(I64 i) { return cells[i]; }
```

```ci run
import geo.vec;                    // used as vec.NAME
import tab as t;                   // or under another name

void main() {
    vec.V3 a = vec.V3(1, 2, 3);
    t.put(2, 7);
    "{vec.dot3(a, a)} {vec.SCALE} {t.get(2)} {t.writes}\n";
}
```

```output
14 10 7 1
```

Imports come first in the file and are not transitive. Another module's array is reached through its
functions (section 4).

### 3.11 Tests

```ci test
I64 twice(I64 x) { return x * 2; }

test "twice doubles" {
    assert(twice(4) == 8);
    assert(twice(0) == 0, "zero stays {twice(0)}");
}

test "overflow is a fault" expect_fault E_OVERFLOW {
    I64 big = I64.max;
    I64 r = twice(big);
}
```

`cint test FILE.ci` prints one line a test and exits 3 when one fails. A failed `assert` on a comparison
reports both operands. A test sees the module's private names and starts from fresh module state. `try` in a
test fails the test when the error leaves it.

### 3.12 Arguments and services

`main` takes nothing, `Grants g`, `in U8[_] args`, or both in that order. The arguments are the words after
`--`, each its bytes and one NUL. `console` and `fs` are the service modules of `lib/`.

```ci run -- alpha beta
import console;

console.ConsoleError!void main(Grants g, in U8[_] args) {
    I64 words = 0;
    for i in 0..len(args) {
        if (args[i] == 0) { words += 1; }
    }
    I64 first = 0;
    while (args[first] != 0) { first += 1; }
    try console.write(g, args[0..first]);      // bytes out as text
    try console.write(g, b"\n");
    "{words} arguments\n";
    return;
}
```

```output
alpha
2 arguments
```

`fs.read`, `fs.stat` and `fs.put` need `requires fs.read("/ROOT");` in the program and a grant on the command
line (`--grant`, SPEC-06P.4 5.4); with no `--grant`, the directory of argument K is readable as `/argK/NAME`.

### 3.13 Kernels

A kernel body is written for one index tuple; its outputs are published when the whole dispatch succeeds.

```ci run
kernel doubled[n](in I64[n] a, out I64[n] b) over [i: n] {
    b[i] = a[i] * 2;
}

void main() {
    I64[4] a = [1, 2, 3, 4];
    I64[4] b;
    doubled(a, b);
    "{b}\n";
}
```

```output
[2, 4, 6, 8]
```

## 4. C9102: forms `cintc` does not compile

C9102 prints "not yet supported by this implementation" at a line and column and does not name the form.
`cintc` gives it for two kinds of form. SPEC-04P.5 6.16 lists constructs that are not part of this edition of
the language: a string type, enumerations, tuples, `var`, `do`, a loop over elements, constant arrays, default
arguments, a view result, `swap` on arrays, `format`, `T.bits` and bit fields. SPEC-09P.5 clause 12 lists
constructs of the edition that the `cint` command of 0.2.17 refuses, among them a step `by` in a range `for`,
a selected import, a module-level array of structs and the hole forms `:c` and `!bits`. A block below checks
that the left column of each row is C9102 in cint 0.2.18. The forms to write are checked in section
3 or in the last block of this section, except those for `swap`, `format` and `random`.

| C9102 in 0.2.18 | write |
| --- | --- |
| `enum Mode : U8 { idle, burn }` | `const I64 IDLE = 0;` and a `switch` with `default` |
| a tuple result `(I64, I64) f()` | a struct result |
| `Str` as a variable, parameter, result or constant; `len("abc")` | `in U8[_]` and `b"..."` |
| `for x in xs`, `for i, x in xs` | `for i in 0..len(xs)` and `xs[i]` |
| `for i in 0..n by 3` | `for (I64 i = 0; i < n; i += 3)`; `by` in a slice compiles |
| `do { } while (c);` | `while` |
| `type Cents = I64;` | the type itself |
| `var total = 5;` | `I64 total = 5;` |
| `const I32[4] P = [2, 3, 5, 7];` | `I32[4] p = [2, 3, 5, 7];` at module level |
| a module-level array of structs | one module-level array for each field, or a local array passed `inout` |
| a module-level array of more than 65,536 elements | a local array of `main`, passed `inout` |
| reading another module's array, `tab.cells[2]` | an exported function of that module |
| `import util.{twice};` | `import util;` and `util.twice` |
| an array argument of a struct constructor, `Body(7, [1, 2, 3])` | declare the struct, then assign the elements |
| `len(ps)` on an array of structs | a size parameter: `f[n](in P[n] ps)` |
| a view result, `in U8[_] front(in U8[_] a)` | return the bounds and slice at the call |
| a default argument, `I64 f(I64 a, I64 b = 10)` | pass every argument |
| `swap(a, b)` | copy through a third array |
| `format(buf, "...")` | fill the bytes in a loop, or print |
| the hole forms `{ch:c}` and `{x!bits:x}` | `console.write` for bytes; `x as% U8` and `{...:x}` |
| printing an error value or an array of rank 2 | a `switch` on the error value; print the elements |
| a call of your own function in a hole after an array hole, `"{xs} {f(1)}"` | put the call in an earlier hole, or in a local first |
| `U8.bits` (`.min` and `.max` compile) | the number |
| a bit field, `U16 mode : 3;` | masks and shifts |
| `random(seed, tick, entity, purpose, draw)` | a wrapping step of your own (section 3.2) |

Four neighbors print other codes: `defer "text";` is C4012 (write `defer { "text"; }`), a local array whose
extent is an ordinary parameter, `I64[n] tmp;`, is C6004 (make `n` a size parameter), a struct in a hole,
`"{p}"`, is C1037 (print its fields), and `w.byte[0]` is C2103.

```ci error C9102
enum Mode : U8 { idle, burn }
void main() { Mode m = .burn; "{m as U8}\n"; }
```

```ci error C9102
(I64, I64) divmod_floor(I64 a, I64 b) { return (a / b, a % b); }
void main() { (I64 q, I64 r) = divmod_floor(-7, 2); "{q} {r}\n"; }
```

```ci error C9102
void main() { Str s = "probe"; "{s}\n"; }
```

```ci error C9102
void show(Str s) { "{s}\n"; }
void main() { show("hi"); }
```

```ci error C9102
void main() { I64[3] xs = [4, 5, 6]; for x in xs { "{x} "; } }
```

```ci error C9102
void main() { for i in 0..10 by 3 { "{i} "; } }
```

```ci error C9102
void main() { I64 i = 3; do { i -= 1; } while (i > 0); "{i}\n"; }
```

```ci error C9102
type Cents = I64;
void main() { Cents c = 5; "{c}\n"; }
```

```ci error C9102
void main() { var total = 5; "{total}\n"; }
```

```ci error C9102
const I32[4] PRIMES = [2, 3, 5, 7];
void main() { "{PRIMES[2]}\n"; }
```

```ci error C9102
struct P { I64 x; I64 y; }
P[4] pts;
void main() { pts[2].y = 9; "{pts[2].y}\n"; }
```

```ci error C9102
U8[65537] cells;
void main() { cells[0] = 1; "{cells[0]}\n"; }
```

```ci module tab.ci
export I64[8] cells;
```

```ci error C9102
import tab;
void main() { "{tab.cells[2]}\n"; }
```

```ci module util.ci
export I64 twice(I64 x) { return x * 2; }
```

```ci error C9102
import util.{twice};
void main() { "{twice(4)}\n"; }
```

```ci error C9102
struct Body { I64 id; I32[3] pos; }
void main() { Body b = Body(7, [1, 2, 3]); "{b.id}\n"; }
```

```ci error C9102
struct P { I64 x; I64 y; }
void main() { P[3] ps; I64 k = len(ps); "{k}\n"; }
```

```ci error C9102
in U8[_] front(in U8[_] a) { return a[0..2]; }
void main() { U8[4] x = b"abcd"; in U8[_] f = front(x); "{f[1]}\n"; }
```

```ci error C9102
I64 f(I64 a, I64 b = 10) { return a + b; }
void main() { "{f(1)}\n"; }
```

```ci error C9102
void main() { I64[3] a = [1, 2, 3]; I64[3] b = [4, 5, 6]; swap(a, b); "{a}\n"; }
```

```ci error C9102
void main() { U8[16] buf; in U8[_] s = format(buf, "abc") catch b"?"; "{len(s)}\n"; }
```

```ci error C9102
void main() { I64 ch = 65; "{ch:c}\n"; }
```

```ci error C9102
void main() { I8 neg = -1; "{neg!bits:x}\n"; }
```

```ci error C9102
error E1 { bad, worse }
void main() { E1 e = .worse; "{e}\n"; }
```

```ci error C9102
void main() { I32[2, 2] m; "{m}\n"; }
```

```ci error C9102
void main() { "{U8.bits}\n"; }
```

```ci error C9102
struct Status { U16 mode : 3; Bool armed : 1; }
void main() { Status s; s.mode = 5; "{s.mode}\n"; }
```

```ci error C9102
void main() { "{random(1, 2, 3, 4, 5)}\n"; }
```

```ci error C9102
I64 f(I64 a) { return a + 1; }
void main() { I64[2] xs = [1, 2]; "{xs} {f(1)}\n"; }
```

```ci error C4012
void main() { defer "second\n"; "first\n"; }
```

```ci error C1037
struct P { I64 x; I64 y; }
void main() { P p = P(1, 2); "{p}\n"; }
```

```ci error C6004
I64 f(I64 n) { I64[n] tmp; tmp[0] = n; return tmp[0]; }
void main() { "{f(10)}\n"; }
```

The forms to write, together:

```ci run
const I64 IDLE = 0;                            // for an enum: typed constants
const I64 BURN = 1;

struct QR { I64 q; I64 r; }                    // for a tuple: a struct result
QR divmod_floor(I64 a, I64 b) { return QR(a / b, a % b); }

I32[4] primes = [2, 3, 5, 7];                  // for a const array: a module-level array
I64[4] pts_x;                                  // for an array of structs at module level:
I64[4] pts_y;                                  // one array for each field

struct Body { I64 id; I32[3] pos; }

I64 next(I64 mode) {
    switch (mode) {
        case IDLE: return BURN;
        default: return IDLE;
    }
}

I64 last[n](in I64[n] a) {                     // a local array sized by a size parameter
    I64[n] tmp;
    for i in 0..n { tmp[i] = a[i] * 2; }
    return tmp[n - 1];
}

void main() {
    QR d = divmod_floor(-7, 2);
    pts_y[2] = 9;
    Body b;                                    // for a constructor with an array: assign the elements
    b.id = 7;
    b.pos[1] = 5;
    I64[3] xs = [4, 5, 6];
    I64 t = 0;
    for i in 0..len(xs) { t += xs[i]; }        // for `for x in xs`
    for (I64 i = 0; i < 10; i += 3) { t += i; }    // for `by`
    I8 neg = -1;
    "{next(IDLE)} {d.q} {d.r} {primes[2]} {pts_y[2]} {b.pos[1]} {t} {last(xs)} {neg as% U8:x}\n";
}
```

```output
1 -4 1 5 9 5 33 12 ff
```

## 5. Diagnostics that print a category

`cint` prints the same sentence for every code of a category. These are the codes met most, each with the
rule it stands for and the repair. The full table is SPEC-04P.5 B.1; the faults are B.2. A heading
here begins with its code, so `cint_primer` with `section` set to a code returns that section.

### C3001: a name declared twice, or a built-in name

Prints "duplicate name" or "is a built-in name". A declaration does not reuse a name in view: a local, a
parameter, a module-level name, an import, or a built-in of section 6. There is no shadowing. A parameter or
local with the name of a function of the same module counts too.

```ci error C3001
void main() {
    I64 count = 1;
    "{count}\n";
}
```

### C4012: a statement form that is not permitted, or a keyword as a name

Prints "statement form not permitted" or "is a keyword". Simple statements are calls, assignments,
increments, prints and declarations: `x + 1;` is not one. A keyword of section 6 where a name is expected is
this code too, reported at the statement's first token with a note at the keyword.

```ci error C4012
void main() {
    I64 by = 1;
    "{by}\n";
}
```

### C1050: a syntax error

Prints "syntax error". Often a keyword in an expression position: `as`, `in` or `catch` used as a name.

```ci error C1050
void main() {
    I64 as = 1;
    "{as}\n";
}
```

### C4011: a result that is not used

Prints "control-flow rule". A call whose function returns a value stands as a statement only as `_ = f();`.
On a `void` call, `_ =` is C2001.

```ci error C4011
I64 f() { return 1; }
void main() {
    f();
}
```

### C2060: a parameter assigned

Prints "parameter or argument rule". Parameters are read-only unless `inout`, and `inout` is for arrays and
structs. Copy a scalar parameter to a local.

```ci error C2060
I64 f(I64 x) {
    x += 1;
    return x;
}
void main() { "{f(1)}\n"; }
```

### C5012: a module-level variable passed to a function that writes it

Prints "parameter mode, alias, or ABI rule". The compiler computes what each function writes, through every
function it calls. An argument that is, or views, a module-level variable that the callee may write is
refused, so that an `in` argument never changes during the call. Pass a copy: a local, or `g + 0`.

```ci error C5012
I64 g = 0;
void bump(I64 v) { g = g + v; }
void main() {
    bump(g);
    "{g}\n";
}
```

```ci run
I64 g = 3;
void bump(I64 v) { g = g + v; }
void main() {
    I64 now = g;
    bump(now);
    bump(g + 0);
    "{g}\n";
}
```

```output
12
```

### C2001: a type mismatch

No implicit conversion exists, widening included. Operands of one operator have one type; an index is `I64`;
`_ =` on a `void` call is this code too.

```ci error C2001
void main() {
    I32 a = 1;
    I64 b = 2;
    I64 c = b + a;
    "{c}\n";
}
```

### C2003: a literal that does not fit its type

A literal takes the type of its context: the declared type, the parameter, or the other operand. So `c < 256`
with a `U8` `c` is this code: write `(c as I64) < 256`.

```ci error C2003
void main() {
    U8 c = 200;
    if (c < 256) { "lt\n"; }
}
```

### C6001: a fault during constant evaluation

An expression of literals is typed first and evaluated at compile time with the run-time rules, so
`I32 x = 1 << 31;` overflows `I32` here. Write the value in a type that holds it.

```ci error C6001
void main() {
    I32 x = 1 << 31;
    "{x}\n";
}
```

### C2002: a condition that is not `Bool`

```ci error C2002
void main() {
    I64 n = 3;
    if (n) { "yes\n"; }
}
```

### C2101: parentheses required

`&&` with `||`, a shift or a bitwise operator with an arithmetic operand, and two different bitwise operators
take parentheses.

```ci error C2101
void main() {
    Bool a = true;
    Bool b = false;
    Bool c = a && b || a;
    "{c}\n";
}
```

### C2102: a chained comparison

```ci error C2102
void main() {
    I64 i = 3;
    if (0 <= i < 5) { "in\n"; }
}
```

### C1043: missing parentheses or braces

`if`, `while` and both `for` forms take braces around the body, and all but the range `for` take parentheses
around the condition.

```ci error C1043
void main() {
    I64 n = 3;
    if (n > 2) "yes\n";
}
```

### C2050: a scalar without an initializer

```ci error C2050
void main() {
    I64 x;
    x = 3;
    "{x}\n";
}
```

### C4001: a path with no `return`

Every loop counts as able to end, `while (true)` included, so a `return` follows it.

```ci error C4001
I64 f() {
    I64 i = 0;
    while (true) {
        i += 1;
        if (i > 3) { return i; }
    }
}
void main() { "{f()}\n"; }
```

### C4023: an empty case body

`case 1: case 2:` does not group. Write `case 1, 2:`.

```ci error C4023
void main() {
    I64 c = 1;
    switch (c) {
        case 1:
        case 2:
            "x\n";
        default:
            "y\n";
    }
}
```

### C3004: a script's variable used in a function

A top-level statement makes the file a script, and a script's variables are locals of its entry. Move the
statements into `void main() { ... }`; the variable is then a module-level variable.

```ci error C3004
I64 balance = 5;
void show() { "{balance}\n"; }
show();
```

### C1035: a hole that is not an expression the hole takes

Prints "invalid character or string literal". A hole holds no string or byte-string literal and no braces,
and a conditional expression in a hole takes parentheses. Compute the value before the print statement.

```ci error C1035
I64 size_of(in U8[_] s) { return len(s); }
void main() {
    "{size_of(b"abc")}\n";
}
```

### E_OVERFLOW: a result outside its type

`+ - * <<`, unary minus and `abs` give the exact result or this fault; nothing wraps without being asked. The
operands' type is the result's type, so widen an operand before the operation, not the result after it. To
wrap write `+%`, to saturate `+|`, and for an error value in place of the fault `add_result` (`sub_result`,
`mul_result`).

```ci fault E_OVERFLOW
void main() {
    I32 a = 2_000_000_000;
    I32 b = a + a;
    "{b}\n";
}
```

```ci run
void main() {
    I32 a = 2_000_000_000;
    I64 wide = (a as I64) + (a as I64);
    I32 wrapped = a +% a;
    I32 top = a +| a;
    I32 checked = add_result(a, a) catch -1;
    "{wide} {wrapped} {top} {checked}\n";
}
```

```output
4000000000 -294967296 2147483647 -1
```

### E_SHIFT: a shift count outside the width

A shift count is 0 to the width less one. `<<` also faults `E_OVERFLOW` when it loses a bit.

```ci fault E_SHIFT
void main() {
    I64 n = 1;
    I64 m = n << 70;
    "{m}\n";
}
```

### E_NARROW: a value that does not fit the destination of `as`

A negative value to an unsigned type is this fault too. `as%` wraps, `as|` saturates, `as?` gives an error.

```ci fault E_NARROW
void main() {
    I64 n = -1;
    U64 u = n as U64;
    "{u}\n";
}
```

### E_DIV_ZERO: a zero divisor

`/`, `%`, `div_trunc`, `rem_trunc`, `div_round` and `muldiv` fault on a zero divisor. No division form wraps
or saturates.

```ci fault E_DIV_ZERO
void main() {
    I64 z = 0;
    I64 q = 5 / z;
    "{q}\n";
}
```

### E_BOUNDS: an index or a slice outside its extent, or a full frame arena

With operation `arena.alloc` the fault is a local array that does not fit the frame arena: see section 3.4.

```ci fault E_BOUNDS
void main() {
    I64[3000000] big;
    big[0] = 1;
    "{big[0]}\n";
}
```

### E_DEPTH: the call depth limit

Recursion is allowed; the depth limit is an input of the run, 256 by default.

```ci fault E_DEPTH
I64 f(I64 n) {
    if (n == 0) { return 0; }
    return f(n - 1) + 1;
}
void main() { "{f(100000)}\n"; }
```

### E_ASSERT: a failed `assert` outside a test

```ci fault E_ASSERT
void main() {
    I64 x = 3;
    assert(x == 4);
}
```

## 6. Names that cannot be identifiers

The keywords (C4012, or C1050 for `as` and `catch`):

```names
as assert break by case catch const continue default defer do else enum errdefer error expect_fault export
extern fallthrough false for if import in in_place inout kernel out over profile reduce requires return
schedule static_assert struct switch test true try type var void where while distinct secret
```

The built-in names (C3001):

```names
len extent size lower copy fill equal swap transpose reverse reshape abs uabs min max clamp div_trunc
rem_trunc div_euclid rem_euclid divmod div_round muldiv mul_full isqrt isqrt_round add_result sub_result
mul_result div_result rem_result shl_result rotl rotr mul div mul_wrap mul_sat sqrt qmul mul_int hadd rhadd
rshr rmulh sum dot fold_checked sum_wrap sum_sat count wrap_bits rescale3 rescale3_rem shl3 sign tdot random
format utf8 embed to_device to_host Round Arena Pool Handle
```

A name of the form `I`, `U`, `Q` or `T` followed by digits, such as `Q32` or `T1`, is reserved for types
(C1010). The rounding modes (`floor`, `ceil`, `trunc`, `away`, `half_even`, `half_away`, `half_trunc`,
`half_up`, `half_down`) are read by position and stay free as names.

## 7. Where the rules are

The paths are those of [cint-public-build](https://github.com/pennyleans/cint-public-build) at 0.2.18.

| need | read |
| --- | --- |
| the rule behind a form | SPEC-04P.5 (`docs/spec/SPEC-04P.5-LANGUAGE.md`): types 6.3, expressions 6.7, declarations 6.9, statements 6.10, errors and faults 6.11, arrays and views 6.12, kernels 6.13, modules and tests 6.15, formatting 7.5 |
| arithmetic and rounding | SPEC-04P.5 6.7 and 7.2 |
| the command and its exit statuses | SPEC-06P.4 clause 5 (`docs/spec/SPEC-06P.4-TOOLS.md`); exit statuses 5.2 |
| every compile code and fault | SPEC-04P.5 B.1 and B.2 |
| the forms `cintc` refuses | SPEC-04P.5 6.16, SPEC-09P.5 clause 12 (`docs/spec/SPEC-09P.5-TOOLCHAIN.md`), `compiler/OPEN.md` and `conformance/unsupported.txt` |
| a worked case of one rule | `conformance/` |
| larger programs in this subset | `examples/ledger.ci`, `toolchain/as/` |
