# Mechanical relocation and support
Inputs: verified published f6a78084+four dirty sources and immutable snapshots. Outputs: canonical modules, legacy alias wrappers, same public functions. Original SQL tables/fields and IO contracts remain in legacy_project schemas.
No business function body changes except __file__ reads mapped to original logical candidate path and private literal lookup at original evaluation point. Flask resource roots use original logical file directory. Controller subprocess mechanism stays intact.
Support contracts: legacy_source_path/legacy_package_path take original relative path and return candidate path; legacy_entry shares import object or runs original CLI retaining argv/cwd/exceptions. private_value loads preserved ignored defaults once, no network.
Assembly copy/read/sha/package/inject/transform are build-only helpers, bounded file reads and streaming hashes; no SQL/ES.
