import os
import json
import base64
import urllib.request
import urllib.error

class TursoRow(tuple):
    """Row that allows access by integer index r[0] or column name r['name']."""
    def __new__(cls, values, cols=None):
        instance = super(TursoRow, cls).__new__(cls, values)
        instance._cols = {col.lower(): i for i, col in enumerate(cols or [])}
        return instance

    def __getitem__(self, key):
        if isinstance(key, str):
            idx = self._cols.get(key.lower())
            if idx is None:
                raise KeyError(f"Column '{key}' not found in row")
            return super().__getitem__(idx)
        return super().__getitem__(key)

    def get(self, key, default=None):
        if isinstance(key, str):
            idx = self._cols.get(key.lower())
            return super().__getitem__(idx) if idx is not None else default
        return super().__getitem__(key)


def _to_turso_arg(val):
    if val is None:
        return {"type": "null"}
    elif isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    elif isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    elif isinstance(val, float):
        return {"type": "float", "value": val}
    elif isinstance(val, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(val).decode()}
    else:
        return {"type": "text", "value": str(val)}


def _from_turso_val(cell):
    t = cell.get("type")
    v = cell.get("value")
    if t == "null":
        return None
    elif t == "integer":
        return int(v)
    elif t == "float":
        return float(v)
    elif t == "text":
        return str(v)
    elif t == "blob":
        return base64.b64decode(cell.get("base64", ""))
    return v


class TursoCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
        self._pos = 0
        self.description = None
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, sql, params=()):
        if not sql or not sql.strip():
            return self
        
        args = [_to_turso_arg(p) for p in params]
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": args
                    }
                },
                {"type": "close"}
            ]
        }

        res = self.conn._send_pipeline(payload)
        first = res.get("results", [{}])[0]
        if first.get("type") == "error":
            err = first.get("error", {})
            raise RuntimeError(f"Turso SQL Error: {err.get('message', 'Unknown error')}")

        result_body = first.get("response", {}).get("result", {})
        col_names = [c.get("name") for c in result_body.get("cols", [])]
        self.description = [(c, None, None, None, None, None, None) for c in col_names]
        
        raw_rows = result_body.get("rows", [])
        parsed_rows = []
        for r in raw_rows:
            parsed_rows.append(TursoRow([_from_turso_val(cell) for cell in r], col_names))
        
        self._rows = parsed_rows
        self._pos = 0
        self.rowcount = result_body.get("affected_row_count", 0)
        self.lastrowid = int(result_body.get("last_insert_rowid", 0) or 0) or None
        return self

    def executescript(self, script):
        # Split statements by semicolon
        stmts = [s.strip() for s in script.split(";") if s.strip()]
        requests = [{"type": "execute", "stmt": {"sql": s}} for s in stmts]
        requests.append({"type": "close"})
        res = self.conn._send_pipeline({"requests": requests})
        for item in res.get("results", []):
            if item.get("type") == "error":
                err = item.get("error", {})
                raise RuntimeError(f"Turso Script Error: {err.get('message')}")
        return self

    def fetchone(self):
        if self._pos < len(self._rows):
            row = self._rows[self._pos]
            self._pos += 1
            return row
        return None

    def fetchall(self):
        rows = self._rows[self._pos:]
        self._pos = len(self._rows)
        return rows


class TursoConnection:
    def __init__(self, url, token):
        # Normalize URL to https://
        clean_url = url.strip()
        if clean_url.startswith("libsql://"):
            clean_url = "https://" + clean_url[len("libsql://"):]
        elif not clean_url.startswith("http://") and not clean_url.startswith("https://"):
            clean_url = "https://" + clean_url

        self.endpoint = clean_url.rstrip("/") + "/v2/pipeline"
        self.token = token.strip() if token else ""

    def _send_pipeline(self, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_content = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Turso HTTP {e.code}: {err_content}")
        except Exception as e:
            raise RuntimeError(f"Turso Connection Error: {str(e)}")

    def cursor(self):
        return TursoCursor(self)

    def execute(self, sql, params=()):
        c = self.cursor()
        return c.execute(sql, params)

    def executescript(self, script):
        c = self.cursor()
        return c.executescript(script)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass
