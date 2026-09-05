# PseInt Dialect Specification (Pinned)

**Version:** 1.0.0  
**Status:** AUTHORITATIVE — pinned dialect for the pseint-judge engine  
**Date:** 2026-09-05  
**Purpose:** This document is the single source of truth for the PseInt dialect the interpreter engine implements. Any future change to the dialect REQUIRES a golden corpus case (≥25) added before the engine change. This is the TDD-lock anchor.

**References:**
- Official PSeInt syntax reference: https://pseint.sourceforge.net/index.php?page=pseudocodigo.php (fetched 2026-09-04)
- Release notes: https://pseint.sourceforge.net/?os=w32&page=actualizacion.php
- Decision ledger: `.omo/drafts/pseint-judge.md` (D1–D17, M1–M13)

---

## (a) Grammar EBNF

The following EBNF describes the complete pinned dialect. Keywords are case-insensitive. Identifiers may contain accented characters and eñe.

```ebnf
program         ::= "Proceso" identifier ["[" param_list "]"] newline block "FinProceso"
param_list      ::= param ("," param)*
param           ::= [direction] identifier [":" type]
direction       ::= "Por Referencia" | "Por Valor"

block           ::= { declaration | statement }

declaration     ::= type_def | dimension_stmt | redimension_stmt
type_def        ::= "Definir" identifier [":" type] ["=" expr] | "Definir" identifier ":" type
dimension_stmt  ::= "Dimension" identifier "[" expr {"," expr} "]"
redimension_stmt:: "Redimensionar" identifier "[" expr {"," expr} "]"

statement       ::= assignment
                  | "Leer" expr_list
                  | "Escribir" [Sin_Saltar] expr_list
                  | if_stmt
                  | "Segun" expr "Hacer" case_list ["De Otro Modo" ":" block] "FinSegun"
                  | while_stmt
                  | "Repetir" block "Hasta Que" expr
                  | for_stmt
                  | "Hacer" block "Mientras Que" expr
                  | "Para" identifier "=" expr "Hasta" expr ["Con Paso" expr] block "FinPara"
                  | "Esperar" expr ["Milisegundos"]
                  | "Limpiar Pantalla"
                  | subproc_call
                  | "Retornar" expr
                  | "SiNo" block  (only valid inside if)

assignment      ::= identifier "<-" expr

if_stmt         ::= "Si" expr "Entonces" block {"SiNo" block} "FinSi"

while_stmt      ::= "Mientras" expr "Hacer" block "FinMientras"

for_stmt        ::= "Para" identifier "=" expr "Hasta" expr ["Con Paso" expr] block "FinPara"

case_list       ::= case_item {case_item}
case_item       ::= case_label ":" block
case_label      ::= integer | "De Otro Modo"

subproc_call    ::= identifier ["(" [expr_list] ")"]

expr_list       ::= expr {"," expr}

expr            ::= logical_or_expr
logical_or_expr ::= logical_and_expr {"|" logical_and_expr}
logical_and_expr:: relational_expr {"&" relational_expr}
relational_expr ::= additive_expr (rel_op additive_expr)*
rel_op          ::= "<" | ">" | "=" | "<>" | "<=" | ">="
additive_expr   ::= multiplicative_expr {("+" | "-") multiplicative_expr}
multiplicative_expr:: unary_expr {("*" | "/" | "%" | "MOD") unary_expr}
unary_expr      ::= ["+" | "-"] power_expr
power_expr      ::= primary_expr ["^" power_expr]
primary_expr    ::= integer | real | string | char | identifier | function_call | "(" expr ")" | "[" expr_list "]"

function_call   ::= identifier "(" [expr_list] ")"

type            ::= "Entero" | "Real" | "Logico" | "Caracter" | "Cadena"

integer         ::= digit {digit}
real            ::= digit {digit} "." digit {digit}
string          ::= '"' {any_char_except_unescaped_double_quote} '"'
char            ::= '"' any_single_char '"'
identifier      ::= letter {letter | digit | "_" | accented_char | "ñ"}
letter          ::= "a".."z" | "A".."Z" | accented_char
accented_char   ::= "á" | "é" | "í" | "ó" | "ú" | "ñ" | "Á" | "É" | "Í" | "Ó" | "Ú" | "Ñ"

comment         ::= "//" {any_char_until_eol}
```

**Notes on the grammar:**
- All keywords are case-insensitive; identifiers are case-sensitive.
- `SiNo` (without space) is accepted as a synonym for `Sino`.
- `HACER...MIENTRAS QUE` is the flexible-syntax variant of `Mientras...Hacer...FinMientras`.
- `De Otro Modo` is the flexible-syntax variant of `Otherwise` in `Segun`.
- Array indexing uses `[expr]` (square brackets), not parentheses.
- The parameter list brackets are optional: `Proceso nombre` and `Proceso nombre [a, b]` are both valid.
- Comments are `//` to end-of-line only; no block comments.
- String literals use double quotes; character literals use double quotes with a single character.

---

## (b) Keyword Table

### Reserved Keywords (case-insensitive)

| Keyword | Category | Flexible Synonyms |
|---------|----------|-------------------|
| Proceso | Program block | — |
| FinProceso | Program end | — |
| Definir | Type declaration | — |
| Dimension | Array declaration | Dimensionar |
| Redimensionar | Array resize | — |
| Leer | Input | — |
| Escribir | Output | — |
| Si | If | — |
| Entonces | Then | — |
| SiNo | Else | Sino |
| FinSi | End if | — |
| Segun | Switch | — |
| Hacer | Do | — |
| FinSegun | End switch | — |
| De Otro Modo | Otherwise | — |
| Mientras | While | — |
| FinMientras | End while | — |
| Repetir | Repeat | — |
| Hasta Que | Until | — |
| Para | For | — |
| Con Paso | With step | — |
| FinPara | End for | — |
| Esperar | Wait | — |
| Milisegundos | Milliseconds | — |
| Limpiar Pantalla | Clear screen | — |
| Retornar | Return | — |
| SubProceso | Subprocedure | — |
| Funcion | Function | — |
| FinSubProceso | End subprocedure | — |
| FinFuncion | End function | — |
| Por Referencia | By reference | — |
| Por Valor | By value | — |

### Logical Constants

| Value | Keywords |
|-------|----------|
| True | Verdadero |
| False | Falso |

### Built-in Functions

| Function | Description |
|----------|-------------|
| AZAR(n) | Random integer [0, n) |
| RC(n) | Random character |
| ABS(n) | Absolute value |
| LN(n) | Natural logarithm |
| EXP(n) | Exponential |
| SEN(n) | Sine |
| COS(n) | Cosine |
| ATAN(n) | Arc tangent |
| TRUNC(n) | Truncate to integer |
| REDON(n) | Round to integer |
| LARGO(s) | Length of string |
| SUBCADENA(s,i,j) | Substring |
| CONCATENAR(s1,s2) | Concatenate strings |
| MAYUSCULARES(s) | Uppercase |
| MINUSCULAS(s) | Lowercase |
| FechaActual | Current date (deterministic stub) |
| HoraActual | Current time (deterministic stub) |

### Flexible-Syntax Synonyms (accepted by lexer, resolved by parser)

| Canonical | Synonyms |
|-----------|----------|
| Dimension | Dimensionar |
| Mientras...Hacer...FinMientras | HACER...MIENTRAS QUE...FINMIENTRAS |
| Sino | SiNo |
| De Otro Modo | Otherwise |
| Con Paso | With step |
| Milisegundos | Milisegundo |

### Accents and eñe in Identifiers

- Identifiers may contain accented vowels (á, é, í, ó, ú, Á, É, Í, Ó, Ú) and eñe (ñ, Ñ).
- The lexer must NOT Unicode-normalize identifiers beyond NFC form.
- Identifiers are case-sensitive: `nombre` and `Nombre` are distinct.
- Accented and non-accented forms are distinct identifiers: `año` ≠ `ano`.
- Keywords remain case-insensitive regardless of accents in the keyword itself (e.g., `mientras`, `MIENTRAS`, `Mientras` all match).

---

## (c) Types and Conversion Matrix

### Base Types

| Type | Literal | Range / Notes |
|------|---------|---------------|
| Entero | integer literal | Arbitrary precision integers |
| Real | real literal (with `.`) | IEEE 754 double precision |
| Logico | Verdadero / Falso | Boolean |
| Caracter | "x" (single char in double quotes) | One character |
| Cadena | "text" (double-quoted) | String of characters |

### Type Declaration

- `Definir` is OPTIONAL under the flexible profile. If omitted, the type is inferred from the first assignment or usage.
- Explicit declaration: `Definir x: Entero` or `Definir x: Entero = 5`.
- Under the flexible profile, `Definir` is accepted but not required.
- Type inference rules:
  - First assignment determines the type.
  - Once inferred, the type is fixed (no re-binding).
  - If no explicit type and no assignment yet, the identifier is untyped until first use.

### Conversion Matrix

| From \ To | Entero | Real | Logico | Caracter | Cadena |
|-----------|--------|------|--------|----------|--------|
| Entero | — | int→real (exact) | 0→Falso, non-zero→Verdadero | int→char (ASCII) | int→string (decimal repr) |
| Real | trunc→int | — | 0.0→Falso, non-zero→Verdadero | trunc→char (ASCII) | real→string (shortest roundtrip) |
| Logico | Verdadero→1, Falso→0 | Verdadero→1.0, Falso→0.0 | — | Verdadero→"Verdadero", Falso→"Falso" | Verdadero→"Verdadero", Falso→"Falso" |
| Caracter | ASCII→int | ASCII→real | — | — | char→string |
| Cadena | parse→int (RE if fail) | parse→real (RE if fail) | "Verdadero"→Verdadero, "Falso"→Falso, else RE | first char | — |

### Arithmetic Rules

- `int / int → real` (division always produces real when both operands are Entero).
- `int * int → int`, `int + int → int`, `int - int → int`.
- `real OP real → real` for all operators.
- `int OP real → real` (int promoted to real).
- `real OP int → real` (int promoted to real).
- Type mismatch in operations (e.g., Logico + Cadena) → RE (ERR_TYPE).
- `%` / `MOD` operates on integers only; if either operand is Real, it is truncated first. If truncation loses precision, RE (ERR_TYPE) is NOT raised — truncation is allowed. But `MOD` on non-numeric types → RE (ERR_TYPE).

### Definir Optional Under Flexible Profile

- Under the flexible profile (default), `Definir` is accepted but not required.
- Type is inferred from the first assignment or literal.
- If `Definir` is present, it must match the inferred type; mismatch → RE (ERR_TYPE).
- This is a deliberate deviation from official PSeInt where `Definir` is mandatory in strict mode.

---

## (d) Operator Precedence

Precedence from highest to lowest (binding tightest first):

| Level | Operators | Associativity |
|-------|-----------|---------------|
| 1 (Primary) | `^` (power) | Right-associative |
| 2 (Unary) | `+`, `-` (unary minus) | Prefix |
| 3 (Multiplicative) | `*`, `/`, `%`, `MOD` | Left-associative |
| 4 (Additive) | `+`, `-` | Left-associative |
| 5 (Relational) | `<`, `>`, `=`, `<>`, `<=`, `>=` | Left-associative |
| 6 (Logical AND) | `&` | Left-associative |
| 7 (Logical OR) | `\|` | Left-associative |
| 8 (Assignment) | `<-` | Right-associative |

- Parentheses `(` `)` override all precedence levels.
- Comparison operators return Logico.
- Logical operators operate on Logico operands; non-Logico operands → RE (ERR_TYPE).
- `&` is logical AND (not bitwise); `\|` is logical OR (not bitwise).
- `<>` means "not equal" (distinct from `=`).

---

## (e) Escribir Formatting Table

### Formatting Rules

| Value Type | Output Format | Example |
|------------|---------------|---------|
| Entero | Integer, no decimal point | `42` |
| Real | Shortest roundtrip float with `.` | `3.14`, `2.0`, `0.5` |
| Logico | `Verdadero` or `Falso` | `Verdadero` |
| Cadena | Raw string, no quotes added | `Hola` |
| Caracter | Raw character, no quotes | `A` |

### Sin Saltar Semantics

- `Escribir Sin Saltar expr_list` prints without a trailing newline.
- `Escribir expr_list` (without `Sin Saltar`) prints with a trailing newline.
- `Sin Saltar` applies to the entire call, not per-argument.
- Multiple arguments in a single `Escribir` call are concatenated with NO separator (no spaces, no commas).

### Multi-Argument Rules

- `Escribir a, b, c` prints the concatenation of `a`, `b`, `c` with no separator.
- If `Sin Saltar` is present, the concatenated output is printed without a trailing newline.
- If `Sin Saltar` is absent, the concatenated output is printed with a trailing newline.

### Golden Examples (verbatim — these become corpus cases in todo 8)

**Example 1: Integer and Real formatting**
```
Proceso Ej1
    Definir x: Entero
    Definir y: Real
    x <- 42
    y <- 3.14
    Escribir x
    Escribir y
FinProceso
```
Expected output:
```
42
3.14
```

**Example 2: Sin Saltar with multiple args**
```
Proceso Ej2
    Escribir Sin Saltar "Resultado: "
    Escribir 100
FinProceso
```
Expected output:
```
Resultado: 100
```

**Example 3: Boolean and string formatting**
```
Proceso Ej3
    Definir flag: Logico
    flag <- Verdadero
    Escribir flag
    Escribir "Hola Mundo"
FinProceso
```
Expected output:
```
Verdadero
Hola Mundo
```

---

## (f) Leer Parsing Rules

### Token Split

- `Leer` reads from standard input.
- Input is split on whitespace (`\s+`).
- Each token is assigned to the next variable in the `Leer` argument list, in order.
- If there are more variables than tokens, the remaining variables get an error (RE: ERR_EOF_INPUT, message "fin de entrada inesperado").
- If there are more tokens than variables, excess tokens are discarded.

### Type Inference

- Each variable's type determines how the token is parsed:
  - Entero: token must parse as integer; otherwise RE (ERR_TYPE).
  - Real: token must parse as real (integer tokens are accepted and promoted); otherwise RE (ERR_TYPE).
  - Logico: token must be "Verdadero" or "Falso" (case-insensitive); otherwise RE (ERR_TYPE).
  - Caracter: token must be exactly one character; otherwise RE (ERR_TYPE).
  - Cadena: token is taken as-is (the entire whitespace-delimited token).
- If `Leer` has no arguments, it reads and discards one line of input.

### EOF Behavior

- If `Leer` encounters EOF before all variables are assigned, the engine raises RE with code ERR_EOF_INPUT and message "fin de entrada inesperado".
- This is a runtime error, not a parse error.

### Multiple Variables

- `Leer a, b, c` reads three tokens from input, assigning them to `a`, `b`, `c` in order.
- All variables must be declared (or inferrable) before `Leer` is executed.

---

## (g) Step-Counting Rules

Each of the following counts as exactly 1 step:

| Construct | Steps |
|-----------|-------|
| Each statement (assignment, Leer, Escribir, etc.) | 1 |
| Each condition evaluation (in Si, Mientras, Hasta Que, Segun) | 1 |
| Each iteration check (the condition re-evaluation in Mientras/Repetir/Hasta Que) | 1 |
| Each built-in function call (AZAR, ABS, LN, etc.) | 1 |
| Each Escribir argument | 1 |
| Each Leer argument | 1 |
| Each operator evaluation within an expression | 1 |
| Recursive function/subprocedure call | The callee body is counted in full (each statement inside the callee counts) |
| Each statement inside a called subprocedure/function | Counts toward the caller's total step count |
| Esperar | 1 step (no-op operation) |
| Cada iteración del bucle Para | 1 step for the body |
| Cada caso en Segun evaluado | 1 step per case condition check |

### Step Counting Details

- **Condition evaluation**: In `Mientras cond Hacer ... FinMientras`, the condition `cond` is evaluated once per iteration. Each evaluation costs 1 step. If the condition is false on the first check, the loop body never executes, but the condition check still costs 1 step.
- **Iteration check**: Same as condition evaluation — each re-evaluation of the loop condition costs 1 step.
- **Recursive calls**: When function `f` calls itself, the entire body of `f` is executed and all its internal steps are counted. There is no special "call overhead" — the callee body IS the step cost.
- **Built-in calls**: Each call to AZAR, ABS, LN, EXP, SEN, COS, ATAN, TRUNC, REDON, LARGO, SUBCADENA, CONCATENAR, MAYUSCULARES, MINUSCULAS, FechaActual, HoraActual costs 1 step.
- **Escribir arguments**: Each argument to Escribir costs 1 step. So `Escribir a, b, c` costs 3 steps.
- **Leer arguments**: Each argument to Leer costs 1 step.
- **Expression evaluation**: Each operator in an expression costs 1 step. So `a + b * c` costs 3 steps (b*c, then a+result).

### Step Budget

- The step budget is a HARD TLE safety cap. If the total steps exceed the budget, the submission receives TLE.
- Default step budget is computed from the expected complexity formula (see section k).
- Problem authors may override with `step_budget` in the problem annotation.

---

## (h) Deterministic Runtime

### AZAR Seeding

- `AZAR(n)` returns a deterministic pseudo-random integer in [0, n).
- The RNG is seeded per run with `test_case.seed` (default 0).
- The seed is set once at the start of each submission execution.
- `AZAR(100)` with seed 0 always produces the same sequence across all runs.
- The specific sequence is pinned by the seed; different seeds produce different sequences.

### FechaActual / HoraActual Stubs

- `FechaActual` returns the deterministic string `2026-01-01`.
- `HoraActual` returns the deterministic string `12:00:00`.
- Combined: `FechaActual` + `HoraActual` = `2026-01-01T12:00:00`.
- These are fixed ISO values; no system clock is consulted.
- This ensures reproducible test results regardless of when the submission is run.

### Esperar

- `Esperar n` is a no-op (does not actually pause execution).
- `Esperar n` costs exactly 1 step.
- `Esperar n Milisegundos` is also a no-op costing 1 step.
- The `n` parameter is parsed but ignored for timing purposes.
- This ensures deterministic step counting and avoids wall-clock delays in the judge.

### Limpiar Pantalla

- `Limpiar Pantalla` is a no-op (no visible output in the judge).
- Costs 1 step.

---

## (i) Runtime-Error Taxonomy

| Code | Name | Trigger |
|------|------|---------|
| ERR_DIV0 | Division by zero | `/` or `MOD` with divisor 0 |
| ERR_TYPE | Type mismatch | Operation on incompatible types, failed type conversion, logical operator on non-Logico |
| ERR_BOUNDS | Array bounds error | Index outside declared dimension bounds |
| ERR_DIM | Dimension error | Accessing undeclared array, Redimensionar on non-array, dimension mismatch |
| ERR_RECURSION | Recursion depth exceeded | Call stack exceeds 1000 frames |
| ERR_EOF_INPUT | Unexpected end of input | Leer runs out of input tokens |
| ERR_STEP_LIMIT | Step limit exceeded | Total steps exceed the problem's step_budget |
| ERR_OUTPUT_CAP | Output cap exceeded | Output exceeds 1 MB |

### Error Behavior

- All runtime errors immediately halt execution of the current submission.
- The verdict is RE (Runtime Error) with the specific error code.
- Parse errors (syntax violations) produce CE (Compile/Parse Error) with a different code scheme.
- Type errors during execution (not parse-time) → ERR_TYPE.
- Division by zero → ERR_DIV0, even if the divisor is a variable that evaluates to 0.
- Array access out of bounds → ERR_BOUNDS.
- Recursion depth > 1000 → ERR_RECURSION.

---

## (j) Comparison Contract

### Output Comparison Rules

1. **Split on `\n`**: The expected output and actual output are each split into lines on the newline character `\n`.
2. **Strip `\r`**: Each line has carriage return characters (`\r`) stripped.
3. **rstrip each line**: Each line has trailing whitespace removed (right-stripped).
4. **Compare line by line**: After the above transformations, lines are compared for exact equality.
5. **Leading whitespace is SIGNIFICANT**: Spaces or tabs at the beginning of a line are preserved and compared.
6. **Blank lines are SIGNIFICANT**: Empty lines in the output must match empty lines in the expected output.
7. **Token mode (optional)**: If `compare_mode = "token"`, each line is split on `\s+` and tokens are compared. This is a per-problem setting.

### Comparison Example

Expected:
```
  Hola
Mundo

```
Actual:
```
  Hola
Mundo

```
After rstrip:
```
  Hola
Mundo

```
Result: MATCH (leading spaces preserved, blank line preserved).

### Token Mode

- In token mode, each line is split by `\s+` (one or more whitespace characters).
- The resulting token lists are compared element by element.
- Leading/trailing whitespace within a line is ignored in token mode.
- Blank lines produce empty token lists.

---

## (k) Complexity Annotation Schema

### Expected Complexity Enum

```
expected_complexity ∈ {O(1), O(log n), O(n), O(n log n), O(n²), O(n³), O(2ⁿ), other}
```

### Step Budget Override

- Each problem may optionally specify `step_budget` as an integer override.
- If `step_budget` is provided, it is used directly as the HARD TLE cap.
- If `step_budget` is NOT provided, it is computed from the formula below.

### Band Formula

```
n_estimate = whitespace-token count of the input
expected = FORMULA(complexity, n_estimate)
band = steps / expected
```

### COEFFICIENT TABLE (NORMATIVE — single source of truth)

| Complexity | Formula | Example (n=10) |
|------------|---------|-----------------|
| O(1) | 50 | 50 |
| O(log n) | 50 · log₂(n + 2) | 50 · log₂(12) ≈ 195 |
| O(n) | 20n + 50 | 250 |
| O(n log n) | 20n · log₂(n + 2) + 50 | 20·10·log₂(12) + 50 ≈ 2050 |
| O(n²) | 5n² + 50 | 550 |
| O(n³) | 2n³ + 50 | 2050 |
| O(2ⁿ) | 2^(n+4) | 2^14 = 16384 |
| other | step_budget REQUIRED (no auto formula) | — |

**Notes:**
- `log₂` means base-2 logarithm, floored to an integer.
- For `O(log n)`: log₂(n + 2), floored to integer, then multiplied by 50.
- For `O(n log n)`: 20 · n · floor(log₂(n + 2)) + 50.
- The coefficient table values are NORMATIVE — todo 13 asserts exact integers from this table. Do not approximate.

### Band Classification

| Band | Condition | Meaning |
|------|-----------|---------|
| OK | steps / expected < 1.5 | Algorithm is efficient enough |
| ALTA | 1.5 ≤ steps / expected < 4 | Algorithm is slower than expected |
| EXCESIVA | steps / expected ≥ 4 | Algorithm is too slow |

### Hard Step Budget (TLE)

```
step_budget = 2 × expected + 1000
```

Unless overridden by `problem.step_budget`.

- If total steps > step_budget → TLE (ERR_STEP_LIMIT).
- The step_budget is a HARD cap, independent of the band classification.
- Even if the band is OK, exceeding the step_budget results in TLE.

### n_estimate Computation

- `n_estimate` = number of whitespace-separated tokens in the problem's input.
- Tokens are counted by splitting the input string on `\s+`.
- Empty input → n_estimate = 0.

---

## Diff-from-Official PSeInt

This section documents every deliberate deviation from official PSeInt behavior. Each deviation includes a one-line rationale.

| # | Deviation | Rationale |
|---|-----------|-----------|
| 1 | `Definir` is optional (type inferred) | Deterministic type rules require unambiguous types; inference removes the need for explicit declarations while preserving correctness |
| 2 | `int / int → real` (not integer division) | Ensures deterministic, predictable results; official PSeInt's integer division behavior varies by version |
| 3 | `AZAR` seeded per run with `test_case.seed` (default 0) | Determinism is a core requirement; official PSeInt uses system time, making tests non-reproducible |
| 4 | `FechaActual` / `HoraActual` return fixed ISO stubs | Deterministic stubs ensure reproducible test results; official PSeInt returns the actual current date/time |
| 5 | `Esperar` is a no-op costing 1 step | Wall-clock delays are incompatible with step-based judging; the step cost preserves the semantic weight |
| 6 | Escribir numbers: integer-as-int, real shortest-roundtrip with `.` | Official PSeInt formatting varies by locale and version; this ensures consistent, predictable output |
| 7 | Escribir multi-arg has no separator | Official PSeInt may add spaces between args; no-separator gives deterministic output |
| 8 | `HACER...MIENTRAS QUE` accepted as flexible synonym | Official PSeInt supports flexible syntax; we pin it explicitly in the spec |
| 9 | Accents and eñe allowed in identifiers | Official PSeInt supports this in flexible profiles; we document it as a first-class feature |
| 10 | Comparison contract: rstrip each line, leading whitespace significant | Official PSeInt comparison is not formally specified; this contract makes grading deterministic |
| 11 | `SiNo` accepted as synonym for `Sino` | Flexible-syntax variant documented in official release notes |
| 12 | Step counting is explicit and normative | No official step-counting standard exists; our custom deterministic op-count is the defensible approach |
| 13 | `MOD` on reals truncates operands first | Prevents ambiguous behavior; official PSeInt does not clearly specify this |
| 14 | `Leer` EOF raises ERR_EOF_INPUT | Official PSeInt behavior on EOF is undefined; explicit error code makes the judge deterministic |
| 15 | Recursion depth cap at 1000 frames | Prevents infinite recursion from crashing the judge; official PSeInt has no documented cap |
| 16 | Output cap at 1 MB | Prevents resource exhaustion; official PSeInt has no output cap |
| 17 | `Limpiar Pantalla` is a no-op | No visible output in the judge; the operation still costs 1 step for semantic consistency |
| 18 | `De Otro Modo` accepted in `Segun` | Official flexible-syntax variant; pinned explicitly |

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-09-05 | Initial pinned dialect spec. Approved as part of the pseint-judge plan. |

---

*This spec is the TDD-lock anchor. Any dialect change requires a golden corpus case first.*
