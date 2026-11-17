-- Ejecuta este script una sola vez con un usuario administrador de MySQL:
--   sudo mysql < sql/create_database.sql
--
-- Crea la base de datos y un usuario de aplicación con permisos solo sobre ella.
-- Cambia la contraseña antes de usar esto fuera de tu máquina.

CREATE DATABASE IF NOT EXISTS obratrack
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'obratrack'@'localhost'
  IDENTIFIED BY 'obratrack_dev';

CREATE USER IF NOT EXISTS 'obratrack'@'127.0.0.1'
  IDENTIFIED BY 'obratrack_dev';

GRANT ALL PRIVILEGES ON obratrack.* TO 'obratrack'@'localhost';
GRANT ALL PRIVILEGES ON obratrack.* TO 'obratrack'@'127.0.0.1';

FLUSH PRIVILEGES;

-- Las tablas las crea la aplicación al arrancar (SQLAlchemy create_all).
-- Para un proyecto en producción se recomienda migrar a Alembic.
