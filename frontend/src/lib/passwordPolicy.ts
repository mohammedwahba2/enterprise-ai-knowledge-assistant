/** Mirrors backend `app.modules.identity.passwords` limits. The server is the authority. */
export const PASSWORD_MIN = 10;
export const PASSWORD_MAX = 128;

export function passwordLengthOk(password: string): boolean {
  const len = [...password.normalize("NFKC")].length; // code points, like the server
  return len >= PASSWORD_MIN && len <= PASSWORD_MAX;
}
