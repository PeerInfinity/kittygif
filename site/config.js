// Single source of truth for what the page loads.  The build script reads the
// wheel name back out of this file's sibling build.json; the Pyodide pin lives
// here so the page and the workflow cannot drift.
window.KITTYGIF = {
  // Pinned exactly: Pyodide ships Pillow as a prebuilt wasm wheel, and which
  // Pillow you get is a property of this version.
  pyodideVersion: "314.0.6",
  cdn: v => `https://cdn.jsdelivr.net/pyodide/v${v}/full/`,
};
