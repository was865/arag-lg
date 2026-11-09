/** 部門・共有リスト・人の API（specs/024）。 */
import createClient from "openapi-fetch";
import type { components, paths } from "@/lib/api/schema";
import { ApiError } from "@/lib/chat/api";
import type { Share } from "@/lib/access/shares";

type S = components["schemas"];
export type DepartmentOut = S["DepartmentOut"];
export type DeptMemberOut = S["DeptMemberOut"];
export type SharesOut = S["SharesOut"];
export type UserKbAccess = S["UserKbAccess"];
export type KbOut = S["KbOut"];

export interface Person {
  id: string;
  name: string;
  email: string;
}

const client = createClient<paths>({ baseUrl: "/api" });

function fail(status: number, error: unknown): never {
  const e = (error as { error?: { code?: string; message?: string } } | undefined)?.error;
  throw new ApiError(status, e?.code ?? "unknown", e?.message ?? "通信に失敗しました。時間をおいてお試しください");
}

async function people(query: string): Promise<unknown> {
  const res = await fetch(`/api/people?${query}`, { cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) fail(res.status, body);
  return body;
}

export const accessApi = {
  async departments() {
    const { data, error, response } = await client.GET("/v1/departments");
    if (!data) fail(response.status, error);
    return data;
  },
  async createDepartment(name: string) {
    const { data, error, response } = await client.POST("/v1/departments", { body: { name } });
    if (!data) fail(response.status, error);
    return data;
  },
  async renameDepartment(id: string, name: string) {
    const { data, error, response } = await client.PATCH("/v1/departments/{dept_id}", {
      params: { path: { dept_id: id } },
      body: { name },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async deleteDepartment(id: string) {
    const { error, response } = await client.DELETE("/v1/departments/{dept_id}", { params: { path: { dept_id: id } } });
    if (!response.ok) fail(response.status, error);
  },
  async departmentMembers(id: string) {
    const { data, error, response } = await client.GET("/v1/departments/{dept_id}/members", {
      params: { path: { dept_id: id } },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async putDepartmentMember(id: string, userId: string, role: "member" | "manager") {
    const { data, error, response } = await client.PUT("/v1/departments/{dept_id}/members/{user_id}", {
      params: { path: { dept_id: id, user_id: userId } },
      body: { role },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async removeDepartmentMember(id: string, userId: string) {
    const { error, response } = await client.DELETE("/v1/departments/{dept_id}/members/{user_id}", {
      params: { path: { dept_id: id, user_id: userId } },
    });
    if (!response.ok) fail(response.status, error);
  },
  async shares(kbId: string) {
    const { data, error, response } = await client.GET("/v1/kbs/{kb_id}/shares", { params: { path: { kb_id: kbId } } });
    if (!data) fail(response.status, error);
    return data;
  },
  async putShares(kbId: string, shares: Share[]) {
    const { data, error, response } = await client.PUT("/v1/kbs/{kb_id}/shares", {
      params: { path: { kb_id: kbId } },
      body: { shares },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async createKb(name: string, departmentId: string | null) {
    const { data, error, response } = await client.POST("/v1/kbs", {
      body: { name, department_id: departmentId },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async manageableKbs() {
    const { data, error, response } = await client.GET("/v1/kbs", { params: { query: { manageable: true } } });
    if (!data) fail(response.status, error);
    return data;
  },
  async userAccess(userId: string) {
    const { data, error, response } = await client.GET("/v1/admin/users/{user_id}/access", {
      params: { path: { user_id: userId } },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async searchPeople(q: string): Promise<Person[]> {
    return ((await people(`q=${encodeURIComponent(q)}`)) as { items: Person[] }).items;
  },
  async resolvePeople(ids: string[]): Promise<Person[]> {
    if (ids.length === 0) return [];
    return ((await people(`ids=${ids.map(encodeURIComponent).join(",")}`)) as { items: Person[] }).items;
  },
  async everyoneIds(): Promise<string[]> {
    return ((await people("all=1")) as { ids: string[] }).ids;
  },
};
