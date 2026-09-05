// SPEC §(i) ERR_RECURSION: infinite recursion
Proceso NegRecursionCap
    Funcion f(n): Entero
        Retornar f(n + 1)
    FinFuncion
    Escribir f(0)
FinProceso
