# Deno KV chunking

Deno KV limits individual values to 64 KiB. The APG cache keeps roughly 48 hours of generation, load, and cross-border data, so a complete cache payload can exceed that limit.

The cache therefore stores each dataset as UTF-8 JSON split into 48,000-byte `Uint8Array` chunks under versioned keys. A small manifest points to the active cache version and records the chunk counts.

Refresh order is intentional:

1. Fetch all APG datasets successfully.
2. Write every chunk for a new cache id.
3. Write the manifest last.

Readers first load the manifest and then reconstruct the three datasets from the referenced chunks. This means a failed refresh cannot expose a partially written cache; the previous manifest remains the last-known-good cache.
