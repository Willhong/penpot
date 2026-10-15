/**
 * In-memory implementation of the Web Storage interface, standing in for the browser's `localStorage` that
 * backs `penpot.localStorage`. Its content lives as long as the executor process (the executor session).
 */
export class MemoryStorage {
    private readonly items = new Map<string, string>();

    get length(): number {
        return this.items.size;
    }

    key(index: number): string | null {
        return [...this.items.keys()][index] ?? null;
    }

    getItem(key: string): string | null {
        return this.items.get(String(key)) ?? null;
    }

    setItem(key: string, value: string): void {
        this.items.set(String(key), String(value));
    }

    removeItem(key: string): void {
        this.items.delete(String(key));
    }

    clear(): void {
        this.items.clear();
    }
}
