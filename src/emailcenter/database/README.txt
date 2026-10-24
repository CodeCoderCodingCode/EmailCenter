SQLite database foundation

Open project databases with emailcenter.database.connect(path). It enables
SQLite foreign-key enforcement for every connection, returns sqlite3.Row rows,
and creates parent folders for file-backed databases.

Apply numbered SQL migrations with:

    connection = connect(project_database_path)
    applied_versions = apply_migrations(connection, migrations_directory)

Migration files use the format NNN_name.sql and contain schema/data statements
only. The migration runner owns transactions, records successful versions in
schema_migrations, updates project_metadata.schema_version when present, and
rolls back a failed migration. Migration scripts must not start or commit their
own transactions. Keep migrations immutable after release.

CompanyRepository and ContactRepository provide parameterized create/read/list
operations and paginated listing. They receive an existing project connection;
application workflows will coordinate them in the application layer.

Project lifecycle functions are in emailcenter.project: create_project(path),
open_project(path), and Project.close(). Project.create_backup() creates a
verified ZIP archive with the manifest, a consistent SQLite snapshot, and
project imports/templates/documents/exports. Temporary and log folders are
excluded. Backups are not encrypted yet; recovery and encryption remain release
work.
