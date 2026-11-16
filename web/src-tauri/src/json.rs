//! The little JSON the shell exchanges with the UI (event payloads): flat
//! objects of strings out, a string or boolean field in. No serde crate (owner
//! decision W8: tauri, tauri-build and the window-state plugin only).

/// A JSON string literal.
pub fn string(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for c in text.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 || c == '\u{2028}' || c == '\u{2029}' => {
                out.push_str(&format!("\\u{:04x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// `{"key": "value", …}`; fields whose value is None are left out.
pub fn object(fields: &[(&str, Option<&str>)]) -> String {
    let body: Vec<String> = fields
        .iter()
        .filter_map(|(key, value)| value.map(|v| format!("{}:{}", string(key), string(v))))
        .collect();
    format!("{{{}}}", body.join(","))
}

/// The string value of `key` in a JSON object (top level only); None when
/// the payload is not an object, lacks the key or holds another type.
pub fn get_string(payload: &str, key: &str) -> Option<String> {
    find(payload, key, Parser::string)
}

/// The boolean value of `key` in a JSON object (top level only), as
/// [`get_string`].
pub fn get_bool(payload: &str, key: &str) -> Option<bool> {
    find(payload, key, Parser::boolean)
}

fn find<T>(payload: &str, key: &str, read: impl FnOnce(&mut Parser) -> Option<T>) -> Option<T> {
    let mut p = Parser {
        chars: payload.chars().collect(),
        at: 0,
    };
    p.space();
    p.eat('{')?;
    loop {
        p.space();
        if p.eat('}').is_some() {
            return None;
        }
        let name = p.string()?;
        p.space();
        p.eat(':')?;
        p.space();
        if name == key {
            return read(&mut p);
        }
        p.skip_value()?;
        p.space();
        p.eat(',')?;
    }
}

struct Parser {
    chars: Vec<char>,
    at: usize,
}

impl Parser {
    fn peek(&self) -> Option<char> {
        self.chars.get(self.at).copied()
    }

    fn eat(&mut self, c: char) -> Option<()> {
        (self.peek() == Some(c)).then(|| self.at += 1)
    }

    fn space(&mut self) {
        while matches!(self.peek(), Some(' ' | '\n' | '\r' | '\t')) {
            self.at += 1;
        }
    }

    fn boolean(&mut self) -> Option<bool> {
        for (word, value) in [("true", true), ("false", false)] {
            let n = word.chars().count();
            if self
                .chars
                .get(self.at..self.at + n)?
                .iter()
                .copied()
                .eq(word.chars())
            {
                self.at += n;
                return Some(value);
            }
        }
        None
    }

    fn hex4(&mut self) -> Option<u32> {
        let digits: String = self.chars.get(self.at..self.at + 4)?.iter().collect();
        self.at += 4;
        u32::from_str_radix(&digits, 16).ok()
    }

    fn string(&mut self) -> Option<String> {
        self.eat('"')?;
        let mut out = String::new();
        loop {
            let c = self.peek()?;
            self.at += 1;
            match c {
                '"' => return Some(out),
                '\\' => {
                    let e = self.peek()?;
                    self.at += 1;
                    match e {
                        '"' | '\\' | '/' => out.push(e),
                        'b' => out.push('\u{8}'),
                        'f' => out.push('\u{c}'),
                        'n' => out.push('\n'),
                        'r' => out.push('\r'),
                        't' => out.push('\t'),
                        'u' => {
                            let mut code = self.hex4()?;
                            if (0xd800..0xdc00).contains(&code) {
                                self.eat('\\')?;
                                self.eat('u')?;
                                let low = self.hex4()?;
                                code = 0x10000
                                    + ((code - 0xd800) << 10)
                                    + (low.checked_sub(0xdc00)?);
                            }
                            out.push(char::from_u32(code)?);
                        }
                        _ => return None,
                    }
                }
                c => out.push(c),
            }
        }
    }

    /// Any value: a string, or everything up to the matching close of an
    /// array / object, or a scalar up to the next `,` `}` `]`.
    fn skip_value(&mut self) -> Option<()> {
        match self.peek()? {
            '"' => self.string().map(|_| ()),
            '{' | '[' => {
                let mut depth = 0usize;
                loop {
                    match self.peek()? {
                        '"' => {
                            self.string()?;
                            continue;
                        }
                        '{' | '[' => depth += 1,
                        '}' | ']' => {
                            depth -= 1;
                            if depth == 0 {
                                self.at += 1;
                                return Some(());
                            }
                        }
                        _ => {}
                    }
                    self.at += 1;
                }
            }
            _ => {
                while !matches!(self.peek(), None | Some(',' | '}' | ']')) {
                    self.at += 1;
                }
                Some(())
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strings_are_escaped() {
        assert_eq!(string("a\"b\\c\nd\u{1}"), "\"a\\\"b\\\\c\\nd\\u0001\"");
        assert_eq!(
            object(&[
                ("phase", Some("ready")),
                ("cause", None),
                ("api", Some("x"))
            ]),
            "{\"phase\":\"ready\",\"api\":\"x\"}"
        );
        assert_eq!(object(&[]), "{}");
    }

    #[test]
    fn a_string_field_is_read_back() {
        let payload = r#" {"n": 1.5e3, "list": [1, {"path": "no"}, "]"], "path": "/Users/o\"b\\s/\u00e9\ud83d\ude00 x"} "#;
        assert_eq!(
            get_string(payload, "path").as_deref(),
            Some("/Users/o\"b\\s/\u{e9}\u{1f600} x")
        );
        assert_eq!(get_string(payload, "n"), None, "not a string");
        assert_eq!(get_string(payload, "missing"), None);
        assert_eq!(get_string("null", "path"), None);
        assert_eq!(get_string("{\"path\": \"unterminated", "path"), None);
        let round = object(&[("path", Some("C:\\a\"b\n"))]);
        assert_eq!(get_string(&round, "path").as_deref(), Some("C:\\a\"b\n"));
    }

    #[test]
    fn a_boolean_field_is_read_back() {
        let payload = r#"{"theme": "night-red", "now": true, "list": [false]}"#;
        assert_eq!(get_bool(payload, "now"), Some(true));
        assert_eq!(get_bool(r#"{"now":false}"#, "now"), Some(false));
        assert_eq!(get_bool(payload, "theme"), None, "not a boolean");
        assert_eq!(get_bool(payload, "missing"), None);
        assert_eq!(get_bool(r#"{"now": tru"#, "now"), None);
    }
}
