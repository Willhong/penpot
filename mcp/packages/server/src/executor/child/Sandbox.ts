import "ses";

declare const Compartment: any;
declare const harden: <T>(value: T) => T;
declare function repairIntrinsics(options: object): void;
declare function hardenIntrinsics(): void;

let intrinsicsRepaired = false;
let intrinsicsHardened = false;

/**
 * Repairs the process's intrinsics with the options the plugins runtime uses in the browser.
 *
 * Must run before the workspace bundle is loaded: repairing removes unknown properties from the intrinsics,
 * and ClojureScript adds its protocol markers to some of them (Error, Date, ...). In the browser the plugins
 * runtime is loaded, and repairs, before the frontend code runs.
 */
export function repairProcessIntrinsics(): void {
    if (intrinsicsRepaired) {
        return;
    }
    intrinsicsRepaired = true;
    repairIntrinsics({
        evalTaming: "unsafeEval",
        stackFiltering: "verbose",
        errorTaming: "unsafe",
        consoleTaming: "unsafe",
        errorTrapping: "none",
        unhandledRejectionTrapping: "none",
    });
}

/**
 * Freezes the process's intrinsics, as the plugins runtime does when it creates the first plugin sandbox.
 * Must run after the workspace is booted, like the plugin starting after the workspace in the browser.
 */
export function hardenProcessIntrinsics(): void {
    if (intrinsicsHardened) {
        return;
    }
    intrinsicsHardened = true;
    hardenIntrinsics();
}

/**
 * Hardens a value handed to user code, as the plugins runtime's `safeReturn` does.
 */
function safeReturn<T>(value: T): T {
    if (value === null || value === undefined) {
        return value;
    }
    return harden(value);
}

/**
 * Proxies an API object so that every value user code obtains from it is hardened, like the plugins
 * runtime's `safeHandler`.
 */
function safeProxy(target: object): object {
    return new Proxy(target, {
        get(obj, prop, receiver) {
            const value = Reflect.get(obj, prop, receiver);
            if (typeof value === "function") {
                return function (...args: unknown[]) {
                    return safeReturn(value.apply(obj, args));
                };
            }
            return safeReturn(value);
        },
    });
}

/**
 * The globals of one execution.
 */
export interface SandboxGlobals {
    penpot: object;
    penpotMgmt: object;
    penpotUtils: object;
    /** the session's storage; kept across executions, so not hardened */
    storage: object;
    console: object;
}

/**
 * SES sandbox for user code (03-runtime-contract §2, D12): every execution gets a new compartment, so its
 * global variables do not survive it. The globals are those of the browser plugin sandbox
 * (`plugins-runtime/src/lib/create-sandbox.ts`) plus the MCP execution globals; there is no `fetch`, module
 * loading, file system or process access.
 */
export class Sandbox {
    /**
     * Runs `code` as the body of an async function in a new compartment and resolves to its return value.
     */
    run(code: string, globals: SandboxGlobals): Promise<unknown> {
        const compartment = new Compartment({
            penpot: safeProxy(globals.penpot),
            penpotMgmt: safeProxy(globals.penpotMgmt),
            penpotUtils: harden(globals.penpotUtils),
            storage: globals.storage,
            console: harden(globals.console),
            setTimeout: harden(setTimeout),
            clearTimeout: harden(clearTimeout),
            setInterval: harden(setInterval),
            clearInterval: harden(clearInterval),
            isFinite: harden(isFinite),
            isNaN: harden(isNaN),
            parseFloat: harden(parseFloat),
            parseInt: harden(parseInt),
            decodeURI: harden(decodeURI),
            decodeURIComponent: harden(decodeURIComponent),
            encodeURI: harden(encodeURI),
            encodeURIComponent: harden(encodeURIComponent),
            Object: harden(Object),
            Boolean: harden(Boolean),
            Symbol: harden(Symbol),
            Number: harden(Number),
            BigInt: harden(BigInt),
            Math: harden(Math),
            Date: harden(Date),
            String: harden(String),
            RegExp: harden(RegExp),
            Array: harden(Array),
            Int8Array: harden(Int8Array),
            Uint8Array: harden(Uint8Array),
            Uint8ClampedArray: harden(Uint8ClampedArray),
            Int16Array: harden(Int16Array),
            Uint16Array: harden(Uint16Array),
            Int32Array: harden(Int32Array),
            Uint32Array: harden(Uint32Array),
            BigInt64Array: harden(BigInt64Array),
            BigUint64Array: harden(BigUint64Array),
            Float32Array: harden(Float32Array),
            Float64Array: harden(Float64Array),
            Map: harden(Map),
            Set: harden(Set),
            WeakMap: harden(WeakMap),
            WeakSet: harden(WeakSet),
            ArrayBuffer: harden(ArrayBuffer),
            DataView: harden(DataView),
            Atomics: harden(Atomics),
            JSON: harden(JSON),
            Promise: harden(Promise),
            Proxy: harden(Proxy),
            Intl: harden(Intl),
            atob: harden(atob),
            btoa: harden(btoa),
            structuredClone: harden(structuredClone),
        });
        const fn = compartment.evaluate(`(async () => { ${code}\n})`);
        return fn();
    }
}
