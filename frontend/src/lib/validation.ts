const USERNAME_PATTERN = /^[A-Za-z0-9_]{3,32}$/

export function validateUsername(value: string): string | null {
  if (!USERNAME_PATTERN.test(value)) {
    return '用户名需为 3–32 位，只能包含英文字母、数字和下划线。'
  }
  return null
}

export function validateStrongPassword(value: string): string | null {
  if (value.length < 12 || value.length > 128) {
    return '密码长度需为 12–128 位。'
  }

  const categories = [
    /[A-Z]/.test(value),
    /[a-z]/.test(value),
    /\d/.test(value),
    /[^A-Za-z0-9]/.test(value),
  ].filter(Boolean).length

  if (categories < 3) {
    return '密码需包含大写字母、小写字母、数字和特殊字符中的至少三类。'
  }

  return null
}

export function safeInternalRedirect(value: unknown): string | null {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) {
    return null
  }
  return value
}