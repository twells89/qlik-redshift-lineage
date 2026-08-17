# Redshift To Snowflake Guidance

This reference is guidance for reviewing the generated migration manifest. It
is not an automatic SQL transpiler.

## Type Mapping

| Redshift | Snowflake | Status | Notes |
|---|---|---|---|
| `SMALLINT` | `SMALLINT` or `NUMBER(5,0)` | AUTO | Preserve integer range |
| `INTEGER` | `INTEGER` or `NUMBER(10,0)` | AUTO | Validate key usage |
| `BIGINT` | `BIGINT` or `NUMBER(19,0)` | AUTO | Check identifiers and joins |
| `DECIMAL(p,s)` / `NUMERIC(p,s)` | `NUMBER(p,s)` | AUTO | Preserve precision and scale |
| `REAL` | `FLOAT` | REVIEW | Aggregate rounding can differ |
| `DOUBLE PRECISION` | `DOUBLE` | REVIEW | Validate tolerance |
| `VARCHAR(n)` | `VARCHAR(n)` | AUTO | Check maximum length and Unicode |
| `CHAR(n)` | `CHAR(n)` | REVIEW | Trailing-space semantics matter |
| `DATE` | `DATE` | AUTO | Usually direct |
| `TIMESTAMP` | `TIMESTAMP_NTZ` | REVIEW | Confirm source timezone semantics |
| `TIMESTAMPTZ` | `TIMESTAMP_TZ` | REVIEW | Validate session/timezone behavior |
| `SUPER` | `VARIANT` | REVIEW | Rewrite JSON access and casts |
| `GEOMETRY` | `GEOMETRY` | REVIEW | Validate function compatibility |

Unknown types are emitted as `VARCHAR` with status `UNSUPPORTED`; they must be
reviewed before DDL execution.

## SQL And Physical Design

- Redshift `DISTKEY`, `SORTKEY`, `ENCODE`, `VACUUM`, and `ANALYZE` are not
  copied into Snowflake DDL. Review clustering and warehouse sizing separately.
- Redshift `SUPER` expressions commonly need `PARSE_JSON`, `VARIANT` path
  notation, explicit casts, and null handling changes.
- Review `GETDATE()`, timestamp casts, session timezone, and date truncation.
- Review `COPY` and `UNLOAD` workflows; Snowflake generally uses stages and
  `COPY INTO`.
- Review identity and sequence behavior rather than copying Redshift defaults.
- Review external schemas, Spectrum tables, late-binding views, and Redshift
  extensions individually.
- Validate blank strings, nulls, trailing spaces, collation, and quoted
  identifier behavior on fields used by Qlik dimensions and joins.
