// SPEC §(b) recursion: factorial(5)=120
Proceso Factorial5
    Funcion fact(n): Entero
        Si n <= 1 Entonces
            Retornar 1
        Sino
            Retornar n * fact(n - 1)
        FinSi
    FinFuncion
    Escribir fact(5)
FinProceso
