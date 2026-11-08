import { ja } from "./locales/ja";

export type Dictionary = typeof ja;

export function getDictionary(): Dictionary {
  return ja;
}
