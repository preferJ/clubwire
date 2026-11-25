// CSRF 토큰만 메모리에 보관한다. 로그인 세션은 서버의 HttpOnly 쿠키로 관리한다.
let csrfToken: string | null = null

export const getUserCsrfToken = () => csrfToken
export const setUserCsrfToken = (token: string | null) => { csrfToken = token }
