// Inicializa el replica set de un nodo (idempotente).
// Obligatorio para transacciones multi-documento: Mongo standalone las rechaza.
try {
  const status = rs.status();
  print(`Replica set ya iniciado: ${status.set}`);
} catch (e) {
  rs.initiate({ _id: "rs0", members: [{ _id: 0, host: "mongo:27017" }] });
  print("Replica set rs0 iniciado.");
}

// Espera a que el nodo sea PRIMARY antes de declarar éxito.
let attempts = 0;
while (attempts < 30) {
  if (db.hello().isWritablePrimary) {
    print("Nodo PRIMARY — transacciones multi-documento disponibles.");
    quit(0);
  }
  sleep(1000);
  attempts++;
}
print("ERROR: el nodo no llegó a PRIMARY en 30s.");
quit(1);
