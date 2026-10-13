// Native commands access one fixed Synth entry, never arbitrary keychain items.
async function sessionCommand(command, args) {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke(command, args);
  } catch (error) {
    throw error instanceof Error ? error : new Error(typeof error === "string" ? error : "Secure session storage is unavailable. Please retry.");
  }
}

export const nativeSessionStorage = {
  async read() {
    return sessionCommand("read_desktop_session");
  },
  async write(credentials) {
    await sessionCommand("write_desktop_session", { credentials });
  },
};
