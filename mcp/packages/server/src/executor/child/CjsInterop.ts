import { readFileSync } from "node:fs";
import { createRequire, findPackageJSON, registerHooks } from "node:module";
import { dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

/** query parameter marking a CommonJS module that is served wrapped */
const MARK = "penpot-cjs-interop";

const IDENTIFIER = /^[A-Za-z_$][A-Za-z0-9_$]*$/;

/**
 * Lets the frontend bundle import CommonJS npm packages by name, as its browser build does.
 *
 * The `:executor` build imports npm packages natively (`import * as sax from "sax"`) and reads their members
 * from the namespace (`sax.parser`). Node only exposes the named exports it can detect statically in a
 * CommonJS module; for packages that assign them at runtime (`sax`) the namespace has nothing but `default`,
 * so SVG parsing failed on the server. CommonJS modules imported from the bundle are served as ES modules
 * that export `module.exports` both as default and member by member.
 *
 * The hooks run in the importing thread (`module.registerHooks`), as the permission model allows no workers.
 *
 * @param bundlePath - path of the `:executor` build's `executor.js`; only imports from its directory are wrapped
 */
export function installCjsInterop(bundlePath: string): void {
    const bundleDir = pathToFileURL(dirname(bundlePath)).href + "/";
    registerHooks({
        resolve(specifier, context, nextResolve) {
            const resolved = nextResolve(specifier, context);
            const fromBundle = context.parentURL?.startsWith(bundleDir) ?? false;
            if (fromBundle && resolved.url.startsWith("file:") && isCommonJs(resolved.url, resolved.format)) {
                return { ...resolved, url: `${resolved.url}?${MARK}`, shortCircuit: true };
            }
            return resolved;
        },
        load(url, context, nextLoad) {
            if (!url.endsWith(`?${MARK}`)) {
                return nextLoad(url, context);
            }
            const path = fileURLToPath(url.slice(0, -MARK.length - 1));
            const exported = createRequire(path)(path);
            const names =
                exported !== null && (typeof exported === "object" || typeof exported === "function")
                    ? Object.keys(exported).filter((name) => IDENTIFIER.test(name) && name !== "default")
                    : [];
            const source = [
                `import { createRequire } from "node:module";`,
                `const m = createRequire(${JSON.stringify(path)})(${JSON.stringify(path)});`,
                `export default m;`,
                ...names.map((name) => `export const ${name} = m[${JSON.stringify(name)}];`),
            ].join("\n");
            return { format: "module", source, shortCircuit: true };
        },
    });
}

/**
 * Whether the module at `url` is CommonJS. The resolve step does not know the format yet for `.js` files,
 * so it is read from the nearest `package.json`, as Node does when it loads them.
 */
function isCommonJs(url: string, format: string | null | undefined): boolean {
    if (format) {
        return format === "commonjs";
    }
    if (url.endsWith(".cjs")) {
        return true;
    }
    if (!url.endsWith(".js")) {
        return false;
    }
    const packageJson = findPackageJSON(url);
    if (!packageJson) {
        return true;
    }
    return JSON.parse(readFileSync(packageJson, "utf8")).type !== "module";
}
