-- Inventario DEMOSTRATIVO. Cuarenta registros ficticios, sin vehículos reales.
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE TABLE IF NOT EXISTS vehiculos (
 id SERIAL PRIMARY KEY, placa VARCHAR(8) NOT NULL UNIQUE, marca VARCHAR(45) NOT NULL,
 linea VARCHAR(60) NOT NULL, modelo INT NOT NULL, categoria VARCHAR(30) NOT NULL,
 combustible VARCHAR(30) NOT NULL, transmision VARCHAR(20) NOT NULL, puestos INT NOT NULL,
 color VARCHAR(25) NOT NULL, maletas INT NOT NULL, precio_dia NUMERIC(12,2) NOT NULL,
 descripcion TEXT NOT NULL DEFAULT '', imagen_url VARCHAR(200) NOT NULL DEFAULT '', activo BOOLEAN NOT NULL DEFAULT TRUE,
 estado VARCHAR(20) NOT NULL DEFAULT 'DISPONIBLE',
 CONSTRAINT ck_inv_precio CHECK (precio_dia > 0));
CREATE TABLE IF NOT EXISTS reservas (
 id SERIAL PRIMARY KEY, orden_id BIGINT NOT NULL, vehiculo_id INT NOT NULL REFERENCES vehiculos(id),
 fecha_inicio DATE NOT NULL, fecha_fin DATE NOT NULL, activa BOOLEAN NOT NULL DEFAULT TRUE,
 CONSTRAINT uq_reserva_orden_vehiculo UNIQUE(orden_id,vehiculo_id),
 CONSTRAINT ck_reserva_fechas CHECK(fecha_fin > fecha_inicio));
-- Protege frente a dos solicitudes concurrentes del mismo vehículo y fechas solapadas.
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ex_reservas_solapadas') THEN
  ALTER TABLE reservas ADD CONSTRAINT ex_reservas_solapadas
    EXCLUDE USING gist (vehiculo_id WITH =, daterange(fecha_inicio,fecha_fin,'[)') WITH &&)
    WHERE (activa = TRUE);
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS movimientos_inventario (
 id SERIAL PRIMARY KEY, vehiculo_id INTEGER NOT NULL, administrador_id BIGINT NOT NULL,
 accion VARCHAR(32) NOT NULL, estado_anterior VARCHAR(20),
 estado_nuevo VARCHAR(20) NOT NULL, observacion TEXT NOT NULL DEFAULT '',
 registrado_en TIMESTAMPTZ NOT NULL DEFAULT NOW());

INSERT INTO vehiculos (id, placa, marca, linea, modelo, categoria, combustible, transmision, puestos, color, maletas, precio_dia, descripcion) VALUES
(1, 'DEMO001', 'Toyota', 'Corolla', 2024, 'Sedán', 'Híbrido', 'Automática', 5, 'Blanco', 3, 190000, 'Vehículo de demostración sedán, 5 puestos, transmisión automática.'),
(2, 'DEMO002', 'Toyota', 'Yaris', 2023, 'Compacto', 'Gasolina', 'Automática', 5, 'Gris', 2, 145000, 'Vehículo de demostración compacto, 5 puestos, transmisión automática.'),
(3, 'DEMO003', 'Toyota', 'RAV4', 2024, 'SUV', 'Híbrido', 'Automática', 5, 'Negro', 4, 295000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(4, 'DEMO004', 'Toyota', 'Hilux', 2023, 'Pickup', 'Diésel', 'Manual', 5, 'Plata', 4, 345000, 'Vehículo de demostración pickup, 5 puestos, transmisión manual.'),
(5, 'DEMO005', 'Chevrolet', 'Onix', 2024, 'Compacto', 'Gasolina', 'Manual', 5, 'Rojo', 2, 142000, 'Vehículo de demostración compacto, 5 puestos, transmisión manual.'),
(6, 'DEMO006', 'Chevrolet', 'Tracker', 2025, 'SUV', 'Gasolina', 'Automática', 5, 'Azul', 3, 218000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(7, 'DEMO007', 'Chevrolet', 'Captiva', 2024, 'SUV', 'Gasolina', 'Automática', 7, 'Gris', 4, 275000, 'Vehículo de demostración suv, 7 puestos, transmisión automática.'),
(8, 'DEMO008', 'Renault', 'Logan', 2022, 'Sedán', 'Gasolina', 'Manual', 5, 'Blanco', 3, 126000, 'Vehículo de demostración sedán, 5 puestos, transmisión manual.'),
(9, 'DEMO009', 'Renault', 'Duster', 2024, 'SUV', 'Gasolina', 'Manual', 5, 'Naranja', 4, 202000, 'Vehículo de demostración suv, 5 puestos, transmisión manual.'),
(10, 'DEMO010', 'Renault', 'Kwid', 2025, 'Compacto', 'Gasolina', 'Manual', 5, 'Azul', 2, 118000, 'Vehículo de demostración compacto, 5 puestos, transmisión manual.'),
(11, 'DEMO011', 'Mazda', '2', 2024, 'Compacto', 'Gasolina', 'Automática', 5, 'Rojo', 2, 178000, 'Vehículo de demostración compacto, 5 puestos, transmisión automática.'),
(12, 'DEMO012', 'Mazda', '3', 2025, 'Sedán', 'Gasolina', 'Automática', 5, 'Plata', 3, 238000, 'Vehículo de demostración sedán, 5 puestos, transmisión automática.'),
(13, 'DEMO013', 'Mazda', 'CX-30', 2024, 'SUV', 'Gasolina', 'Automática', 5, 'Azul', 3, 269000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(14, 'DEMO014', 'Kia', 'Picanto', 2023, 'Compacto', 'Gasolina', 'Manual', 5, 'Blanco', 2, 122000, 'Vehículo de demostración compacto, 5 puestos, transmisión manual.'),
(15, 'DEMO015', 'Kia', 'Rio', 2024, 'Sedán', 'Gasolina', 'Automática', 5, 'Negro', 3, 174000, 'Vehículo de demostración sedán, 5 puestos, transmisión automática.'),
(16, 'DEMO016', 'Kia', 'Sportage', 2025, 'SUV', 'Híbrido', 'Automática', 5, 'Gris', 4, 318000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(17, 'DEMO017', 'Hyundai', 'i10', 2024, 'Compacto', 'Gasolina', 'Manual', 5, 'Plata', 2, 123000, 'Vehículo de demostración compacto, 5 puestos, transmisión manual.'),
(18, 'DEMO018', 'Hyundai', 'Accent', 2023, 'Sedán', 'Gasolina', 'Automática', 5, 'Azul', 3, 173000, 'Vehículo de demostración sedán, 5 puestos, transmisión automática.'),
(19, 'DEMO019', 'Hyundai', 'Tucson', 2025, 'SUV', 'Híbrido', 'Automática', 5, 'Blanco', 4, 315000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(20, 'DEMO020', 'Nissan', 'Versa', 2024, 'Sedán', 'Gasolina', 'Automática', 5, 'Plata', 3, 172000, 'Vehículo de demostración sedán, 5 puestos, transmisión automática.'),
(21, 'DEMO021', 'Nissan', 'Kicks', 2025, 'SUV', 'Gasolina', 'Automática', 5, 'Negro', 3, 225000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(22, 'DEMO022', 'Nissan', 'X-Trail', 2024, 'SUV', 'Gasolina', 'Automática', 7, 'Blanco', 5, 330000, 'Vehículo de demostración suv, 7 puestos, transmisión automática.'),
(23, 'DEMO023', 'Volkswagen', 'Polo', 2024, 'Compacto', 'Gasolina', 'Automática', 5, 'Rojo', 2, 185000, 'Vehículo de demostración compacto, 5 puestos, transmisión automática.'),
(24, 'DEMO024', 'Volkswagen', 'Virtus', 2025, 'Sedán', 'Gasolina', 'Automática', 5, 'Azul', 3, 207000, 'Vehículo de demostración sedán, 5 puestos, transmisión automática.'),
(25, 'DEMO025', 'Volkswagen', 'T-Cross', 2024, 'SUV', 'Gasolina', 'Automática', 5, 'Plata', 3, 249000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(26, 'DEMO026', 'Suzuki', 'Swift', 2024, 'Compacto', 'Híbrido', 'Manual', 5, 'Gris', 2, 145000, 'Vehículo de demostración compacto, 5 puestos, transmisión manual.'),
(27, 'DEMO027', 'Suzuki', 'Vitara', 2023, 'SUV', 'Gasolina', 'Automática', 5, 'Blanco', 3, 209000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(28, 'DEMO028', 'Ford', 'Escape', 2024, 'SUV', 'Híbrido', 'Automática', 5, 'Azul', 4, 302000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(29, 'DEMO029', 'Ford', 'Ranger', 2025, 'Pickup', 'Diésel', 'Automática', 5, 'Negro', 4, 395000, 'Vehículo de demostración pickup, 5 puestos, transmisión automática.'),
(30, 'DEMO030', 'Ford', 'Bronco Sport', 2024, 'SUV', 'Gasolina', 'Automática', 5, 'Verde', 4, 362000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(31, 'DEMO031', 'Jeep', 'Renegade', 2024, 'SUV', 'Gasolina', 'Automática', 5, 'Rojo', 3, 282000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(32, 'DEMO032', 'Jeep', 'Compass', 2025, 'SUV', 'Gasolina', 'Automática', 5, 'Plata', 4, 342000, 'Vehículo de demostración suv, 5 puestos, transmisión automática.'),
(33, 'DEMO033', 'BMW', '320i', 2024, 'Premium', 'Gasolina', 'Automática', 5, 'Negro', 3, 520000, 'Vehículo de demostración premium, 5 puestos, transmisión automática.'),
(34, 'DEMO034', 'BMW', 'X1', 2025, 'Premium', 'Gasolina', 'Automática', 5, 'Blanco', 3, 545000, 'Vehículo de demostración premium, 5 puestos, transmisión automática.'),
(35, 'DEMO035', 'Mercedes-Benz', 'A 200', 2024, 'Premium', 'Gasolina', 'Automática', 5, 'Gris', 3, 535000, 'Vehículo de demostración premium, 5 puestos, transmisión automática.'),
(36, 'DEMO036', 'Mercedes-Benz', 'GLA 200', 2025, 'Premium', 'Gasolina', 'Automática', 5, 'Azul', 4, 578000, 'Vehículo de demostración premium, 5 puestos, transmisión automática.'),
(37, 'DEMO037', 'Audi', 'A3', 2024, 'Premium', 'Gasolina', 'Automática', 5, 'Negro', 3, 495000, 'Vehículo de demostración premium, 5 puestos, transmisión automática.'),
(38, 'DEMO038', 'Audi', 'Q3', 2025, 'Premium', 'Gasolina', 'Automática', 5, 'Blanco', 4, 563000, 'Vehículo de demostración premium, 5 puestos, transmisión automática.'),
(39, 'DEMO039', 'BYD', 'Dolphin', 2025, 'Eléctrico', 'Eléctrico', 'Automática', 5, 'Celeste', 3, 278000, 'Vehículo de demostración eléctrico, 5 puestos, transmisión automática.'),
(40, 'DEMO040', 'Tesla', 'Model 3', 2025, 'Eléctrico', 'Eléctrico', 'Automática', 5, 'Gris', 3, 475000, 'Vehículo de demostración eléctrico, 5 puestos, transmisión automática.')
ON CONFLICT (id) DO NOTHING;
SELECT setval(pg_get_serial_sequence('vehiculos','id'), (SELECT MAX(id) FROM vehiculos));

-- Asociar una foto ilustrativa a los 40 registros de catálogo; imágenes alojadas en el frontend.
UPDATE vehiculos SET imagen_url = '/vehicles/car-' || lpad(((id-1)%40+1)::text,2,'0') || '.webp' WHERE imagen_url='' OR imagen_url IS NULL;
