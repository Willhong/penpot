/**
 * Record of the Plugin API members user code reads, writes or calls, for the PEN-9 coverage run.
 *
 * Enabled by `PENPOT_EXECUTOR_TRACE_API=1`. Each object user code gets from the API is wrapped in a proxy
 * that records `<kind>.<member>`, where the kind is the object's `Symbol.toStringTag` (`ShapeProxy`,
 * `PageProxy`, ...; shapes and tokens add their `type`, as in `ShapeProxy:rectangle`) or, for a plain object, the path
 * it was reached by (`penpot.utils.geometry`). At the end of each execution the members it touched go to
 * stdout as one line starting with {@link ApiTrace.MARKER}. Values passed back into the API are unwrapped,
 * so the API sees its own objects.
 *
 * The wrapper goes outside the sandbox's hardening proxy. The objects it wraps are frozen, and a proxy
 * may not report another value for a frozen property, so each proxy has an empty stand-in as its target
 * and forwards every operation to the real object. Arrays come back as new arrays of wrapped items.
 */
export class ApiTrace {
    static readonly MARKER = "[api-trace] ";

    private readonly wrapped = new WeakMap<object, object>();
    private readonly targets = new WeakMap<object, object>();
    private members = new Set<string>();

    /**
     * @param write where flushed lines go; stdout, which the MCP server's log keeps
     */
    constructor(private readonly write: (line: string) => void = (line) => process.stdout.write(line)) {}

    /**
     * Wraps a root API object (`penpot`, `penpotMgmt`) for user code.
     */
    wrap(target: object, kind: string): object {
        return this.wrapValue(target, kind);
    }

    /**
     * Writes the members recorded since the last flush, and starts a new record.
     */
    flush(): void {
        if (this.members.size > 0) {
            this.write(ApiTrace.MARKER + JSON.stringify([...this.members].sort()) + "\n");
        }
        this.members = new Set();
    }

    private kindOf(target: object, path: string): string {
        const tag = (target as any)[Symbol.toStringTag];
        if (typeof tag !== "string" || tag === "Object") {
            return path;
        }
        if (tag === "ShapeProxy" || tag === "TokenProxy") {
            return `${tag}:${(target as any).type}`;
        }
        return tag;
    }

    private unwrap(value: unknown): unknown {
        if (value !== null && typeof value === "object") {
            const target = this.targets.get(value);
            if (target) {
                return target;
            }
            if (Array.isArray(value)) {
                return value.map((item) => this.unwrap(item));
            }
            // data user code builds, such as `{ destination: board }`, may hold API objects
            const proto = Object.getPrototypeOf(value);
            if (proto === Object.prototype || proto === null) {
                return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, this.unwrap(item)]));
            }
        }
        return value;
    }

    private wrapFunction(fn: Function, owner: object, path: string): Function {
        const trace = this;
        return function (...args: unknown[]) {
            const result = fn.apply(
                owner,
                args.map((arg) => trace.unwrap(arg))
            );
            return result instanceof Promise
                ? result.then((resolved) => trace.wrapValue(resolved, `${path}()`))
                : trace.wrapValue(result, `${path}()`);
        };
    }

    private wrapValue(value: unknown, path: string): any {
        if (
            value === null ||
            typeof value !== "object" ||
            value instanceof Promise ||
            ArrayBuffer.isView(value) ||
            value instanceof ArrayBuffer
        ) {
            return value;
        }
        if (Array.isArray(value)) {
            return value.map((item) => this.wrapValue(item, path));
        }
        const target = value as object;
        const known = this.wrapped.get(target);
        if (known) {
            return known;
        }
        const trace = this;
        const proxy = new Proxy(Object.create(Object.getPrototypeOf(target)), {
            get(_, prop) {
                const member = Reflect.get(target, prop, target);
                if (typeof prop === "symbol") {
                    return member;
                }
                const kind = trace.kindOf(target, path);
                trace.members.add(`${kind}.${prop}`);
                return typeof member === "function"
                    ? trace.wrapFunction(member, target, `${kind}.${prop}`)
                    : trace.wrapValue(member, `${kind}.${prop}`);
            },
            set(_, prop, value) {
                if (typeof prop === "string") {
                    trace.members.add(`${trace.kindOf(target, path)}.${prop}`);
                }
                // a plain (strict mode) assignment, so a refused write throws the API's own error
                (target as any)[prop] = trace.unwrap(value);
                return true;
            },
            has: (_, prop) => Reflect.has(target, prop),
            ownKeys: () => Reflect.ownKeys(target),
            getOwnPropertyDescriptor(_, prop) {
                const descriptor = Reflect.getOwnPropertyDescriptor(target, prop);
                if (descriptor) {
                    // the stand-in has no such property, so the proxy may not call it non-configurable
                    descriptor.configurable = true;
                }
                return descriptor;
            },
            defineProperty: (_, prop, descriptor) => Reflect.defineProperty(target, prop, descriptor),
            deleteProperty: (_, prop) => Reflect.deleteProperty(target, prop),
        });
        this.wrapped.set(target, proxy);
        this.targets.set(proxy, target);
        return proxy;
    }
}
