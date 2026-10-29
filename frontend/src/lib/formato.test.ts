import { describe, expect, it } from "vitest";

import { editarMoeda, lerMoeda } from "./formato";

describe("máscara de moeda", () => {
  it("lê valores no formato brasileiro", () => {
    expect(lerMoeda("1.234,56")).toBe(1234.56);
    expect(lerMoeda("0,00")).toBe(0);
  });
  it("vazio é não informado (diferente de zero)", () => {
    expect(lerMoeda("")).toBeNull();
  });
  it("formata para edição", () => {
    expect(editarMoeda(1234.5)).toBe("1.234,50");
    expect(editarMoeda(null)).toBe("");
  });
});
