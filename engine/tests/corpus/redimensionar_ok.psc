// SPEC §(a) Redimensionar preserves data
Proceso RedimensionarOk
    Dimension a[3]
    a[0] <- 7
    a[1] <- 8
    Redimensionar a[5]
    a[4] <- 9
    Escribir a[0], a[1], a[4]
FinProceso
