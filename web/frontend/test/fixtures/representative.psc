// SPEC §(b) keyword coverage fixture
// Derived from engine/tests/corpus patterns: si_sino.psc, mientras_basico.psc,
// segun_default.psc, esperar_limpiar.psc, factorial_5.psc, synonym_*.psc
Proceso Cobertura
    Definir n: Entero
    Definir x: Real
    Definir flag: Logico
    Definir c: Caracter
    Definir s: Cadena
    Dimension arr[5]
    Dimensionar arr2[3]
    Redimensionar arr[10]
    n <- 5
    x <- 3.14
    flag <- Verdadero
    flag <- Falso
    c <- "A"
    s <- "hola"
    Escribir Sin Saltar "n="
    Escribir n
    Leer n
    Si n > 0 Y n < 10 O n = 5 Entonces
        Escribir "positivo"
    Sino
        Escribir "negativo"
    FinSi
    Si NO flag Entonces
        Escribir "falso"
    FinSi
    Segun n Hacer
        1: Escribir "uno"
        De Otro Modo: Escribir "otro"
    FinSegun
    Segun n Hacer
        1: Escribir "uno"
        Otherwise: Escribir "otro"
    FinSegun
    Mientras n < 10 Hacer
        n <- n + 1
    FinMientras
    Repetir
        n <- n - 1
    Hasta Que n = 0
    Para i <- 1 Hasta 5 Con Paso 1
        Escribir i
    FinPara
    Para j <- 1 Hasta 3 With step 1
        Escribir j
    FinPara
    Esperar 100 Milisegundos
    Esperar 50 Milisegundo
    Limpiar Pantalla
    Escribir n MOD 2
    Escribir n / 2
    Escribir n ^ 2
    Escribir n % 3
    Escribir n & 1 | 0 ~ flag
    Escribir n == 5
    Escribir n <> 5
    Escribir n <= 5
    Escribir n >= 5
    Escribir AZAR(10)
    Escribir RC()
    Escribir ABS(-5)
    Escribir LN(1)
    Escribir EXP(1)
    Escribir SEN(0)
    Escribir COS(0)
    Escribir ATAN(0)
    Escribir TRUNC(1.9)
    Escribir REDON(1.5)
    Escribir LARGO(s)
    Escribir SUBCADENA(s, 1, 2)
    Escribir CONCATENAR(s, s)
    Escribir MAYUSCULARES(s)
    Escribir MINUSCULAS(s)
    Escribir FechaActual
    Escribir HoraActual
    Funcion Doble(v): Entero
        Retornar v * 2
    FinFuncion
    SubProceso Saludar(nombre Por Valor)
        Escribir nombre
    FinSubProceso
    SubProceso Cambiar(nombre Por Referencia)
        Escribir nombre
    FinSubProceso
    Escribir Doble(5)
FinProceso