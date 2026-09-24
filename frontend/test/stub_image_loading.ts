type Outcome = "load" | "error";

let outcome: Outcome = "load";

/** jsdom never loads images, but Radix's Avatar only renders its <img> once
 * a preloading `new Image()` reports success. This makes that preloader
 * finish deterministically; `"error"` simulates an expired or deleted
 * avatar. `test/setup.ts` resets it to `"load"` after every test. */
export function setImageLoadOutcome(next: Outcome): void {
  outcome = next;
}

export function installImageLoadingStub(): void {
  window.Image = function FakeImage() {
    const image = document.createElement("img");
    let src = "";
    let settled = false;
    Object.defineProperty(image, "complete", { get: () => settled });
    Object.defineProperty(image, "naturalWidth", {
      get: () => (settled && outcome === "load" ? 1 : 0),
    });
    Object.defineProperty(image, "src", {
      get: () => src,
      set: (value: string) => {
        src = value;
        setTimeout(() => {
          settled = true;
          image.dispatchEvent(new Event(outcome));
        });
      },
    });
    return image;
  } as unknown as typeof window.Image;
}
