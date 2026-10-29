# Internal Pokémon Black runtime slot

This directory is a private build/package slot for the native runtime used by the unified launcher. It is not a second user-facing application and the player must never browse for or launch its executable manually.

The runtime is intentionally not included in public builds at this stage. The pinned Aletheia game-source directory currently does not grant a clear redistribution license for the reconstructed game code or derivatives. For private local development tests only, the staging helper may place a user-built native payload in the `runtime/` child directory; that directory is ignored by Git and must never be uploaded as a public artifact or release until the licensing question is resolved by an appropriate review.

When redistribution is authorized, the packaging pipeline may stage the platform-specific native runtime here as an internal resource of the Platina Reluzente launcher. The game must continue to import only user-provided local ROM data, and Black's extracted assets, configuration, saves and logs must remain isolated from Platinum.

The current launcher checks this directory at runtime and keeps the Black Play action disabled while the internal executable is absent.
