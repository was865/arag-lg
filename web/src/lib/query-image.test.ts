import { describe, expect, it } from "vitest";
import { checkImageFile, fitWithin, imageFromClipboard, QUERY_IMAGE_TYPES } from "./query-image";

const file = (type: string, size = 10) => new File([new Uint8Array(size)], "x", { type });

describe("fitWithin", () => {
  it("長辺を上限に合わせて縮め、縦横比を保つ", () => {
    expect(fitWithin(3200, 1600, 1600)).toEqual({ width: 1600, height: 800 });
    expect(fitWithin(1000, 3000, 1600)).toEqual({ width: 533, height: 1600 });
  });
  it("小さい画像は拡大しない", () => {
    expect(fitWithin(640, 480, 1600)).toEqual({ width: 640, height: 480 });
  });
});

describe("checkImageFile", () => {
  it("対応形式は通す", () => {
    for (const t of QUERY_IMAGE_TYPES) expect(checkImageFile(file(t))).toBeNull();
  });
  it("画像以外・未対応の形式・大きすぎるものは理由を返す", () => {
    expect(checkImageFile(file("application/pdf"))).toMatch("JPEG");
    expect(checkImageFile(file("image/heic"))).toMatch("JPEG");
    expect(checkImageFile(file("image/png", 30 * 1024 * 1024))).toMatch("20MB");
  });
});

describe("imageFromClipboard", () => {
  it("貼り付けた中から最初の画像ファイルを取り出す", () => {
    const png = file("image/png");
    const dt = { files: [file("text/plain"), png] } as unknown as DataTransfer;
    expect(imageFromClipboard(dt)).toBe(png);
    expect(imageFromClipboard({ files: [file("text/plain")] } as unknown as DataTransfer)).toBeNull();
    expect(imageFromClipboard(null)).toBeNull();
  });
});
