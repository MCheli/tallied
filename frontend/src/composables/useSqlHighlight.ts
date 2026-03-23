/**
 * Lightweight SQL syntax highlighter.
 * Returns an HTML string with <span> classes for keywords, strings, numbers, comments, and functions.
 */

const KEYWORDS = new Set([
  'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'IS', 'NULL', 'AS',
  'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'CROSS', 'ON', 'USING',
  'GROUP', 'BY', 'ORDER', 'HAVING', 'LIMIT', 'OFFSET', 'UNION', 'ALL',
  'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE', 'CREATE', 'DROP',
  'ALTER', 'TABLE', 'INDEX', 'VIEW', 'WITH', 'RECURSIVE', 'DISTINCT',
  'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'BETWEEN', 'LIKE', 'EXISTS',
  'TRUE', 'FALSE', 'ASC', 'DESC', 'NULLS', 'FIRST', 'LAST',
  'EXPLAIN', 'ANALYZE', 'GRANT', 'REVOKE', 'TRUNCATE',
])

const FUNCTIONS = new Set([
  'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COALESCE', 'CAST',
  'DATE', 'STRFTIME', 'ROUND', 'ABS', 'IFNULL', 'NULLIF',
  'LENGTH', 'SUBSTR', 'REPLACE', 'TRIM', 'UPPER', 'LOWER',
  'GROUP_CONCAT', 'ROW_NUMBER', 'RANK', 'DENSE_RANK',
])

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function highlightSql(sql: string): string {
  const tokens: string[] = []
  let i = 0

  while (i < sql.length) {
    // Single-line comment
    if (sql[i] === '-' && sql[i + 1] === '-') {
      const end = sql.indexOf('\n', i)
      const comment = end === -1 ? sql.slice(i) : sql.slice(i, end)
      tokens.push(`<span class="sql-comment">${escapeHtml(comment)}</span>`)
      i += comment.length
      continue
    }

    // Block comment
    if (sql[i] === '/' && sql[i + 1] === '*') {
      const end = sql.indexOf('*/', i + 2)
      const comment = end === -1 ? sql.slice(i) : sql.slice(i, end + 2)
      tokens.push(`<span class="sql-comment">${escapeHtml(comment)}</span>`)
      i += comment.length
      continue
    }

    // String literal
    if (sql[i] === "'") {
      let j = i + 1
      while (j < sql.length) {
        if (sql[j] === "'" && sql[j + 1] === "'") { j += 2; continue }
        if (sql[j] === "'") { j++; break }
        j++
      }
      tokens.push(`<span class="sql-string">${escapeHtml(sql.slice(i, j))}</span>`)
      i = j
      continue
    }

    // Number
    if (/\d/.test(sql[i]) && (i === 0 || /[\s,=(]/.test(sql[i - 1]))) {
      let j = i
      while (j < sql.length && /[\d.]/.test(sql[j])) j++
      tokens.push(`<span class="sql-number">${escapeHtml(sql.slice(i, j))}</span>`)
      i = j
      continue
    }

    // Word (keyword, function, or identifier)
    if (/[a-zA-Z_]/.test(sql[i])) {
      let j = i
      while (j < sql.length && /[a-zA-Z0-9_]/.test(sql[j])) j++
      const word = sql.slice(i, j)
      const upper = word.toUpperCase()

      if (KEYWORDS.has(upper)) {
        tokens.push(`<span class="sql-keyword">${escapeHtml(word)}</span>`)
      } else if (FUNCTIONS.has(upper) || (j < sql.length && sql[j] === '(')) {
        tokens.push(`<span class="sql-function">${escapeHtml(word)}</span>`)
      } else {
        tokens.push(escapeHtml(word))
      }
      i = j
      continue
    }

    // Operators
    if ('*.,;()=<>!+-/'.includes(sql[i])) {
      tokens.push(`<span class="sql-operator">${escapeHtml(sql[i])}</span>`)
      i++
      continue
    }

    // Whitespace / other
    tokens.push(escapeHtml(sql[i]))
    i++
  }

  return tokens.join('')
}
