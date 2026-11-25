# GitHub Pages source

`index.html`, `examples.html`, `guide.html`, `status.html` are page body templates, not independently deployable pages. `catalog.json` owns the hosted example inventory. `media/` contains small, actual project-rendered previews from 0.21–0.23; the full fields stay in `assets/`. The builder applies the common layout, status and availability, copies only public browser examples and their dependencies, and validates local links.

From the repository root:

```sh
python tools/build_pages.py --assets auto
python -m http.server 8000 --bind 127.0.0.1 --directory dist/pages
```

Use `--assets none` for a source-only site or `--assets full` to require all hosted sample fields. `auto` includes each complete asset group and otherwise displays local-only guidance. No native/WASM binaries or `history/` data are published. The generated site is `dist/pages/`, not this template directory. It works under a project subpath (`/<repository>/`) because all local paths are relative.

Deployment is manual and gated by a redistribution-rights acknowledgement. See [publishing guide](../docs/PUBLISHING_KO.md).
