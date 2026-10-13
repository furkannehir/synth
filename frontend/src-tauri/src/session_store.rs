use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex};
use tauri::{State, WebviewWindow};

#[derive(Default)]
pub struct SessionStore(pub Arc<Mutex<()>>);

#[derive(Deserialize, Serialize)]
pub struct SavedSession {
    refresh_token: String,
    revocation_token: String,
    next_refresh_token: Option<String>,
}

#[derive(Default, Deserialize, Serialize)]
pub struct Credentials {
    session: Option<SavedSession>,
    pending_revocations: Vec<String>,
}

fn validate_credentials(value: &Credentials) -> Result<(), String> {
    let valid = |token: &str| {
        token.len() == 76
            && token.as_bytes()[32] == b'.'
            && token[..32]
                .bytes()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
            && token[33..]
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
    };
    if value.pending_revocations.len() > 32
        || value.pending_revocations.iter().any(|token| !valid(token))
        || value.session.as_ref().is_some_and(|session| {
            !valid(&session.refresh_token)
                || !valid(&session.revocation_token)
                || session
                    .next_refresh_token
                    .as_ref()
                    .is_some_and(|token| !valid(token))
        })
    {
        return Err("Invalid saved session.".into());
    }
    Ok(())
}

pub fn is_app_url(url: &tauri::Url) -> bool {
    if !url.username().is_empty() || url.password().is_some() {
        return false;
    }
    match url.scheme() {
        "tauri" => url.host_str() == Some("localhost") && url.port().is_none(),
        "http" | "https" => {
            (url.host_str() == Some("tauri.localhost") && url.port().is_none())
                || (cfg!(debug_assertions)
                    && url.host_str() == Some("localhost")
                    && url.port() == Some(5173))
        }
        _ => false,
    }
}

fn check_window(window: &WebviewWindow) -> Result<(), String> {
    let url = window.url().map_err(|_| "Unable to verify app window.")?;
    if window.label() != "main" || !is_app_url(&url) {
        return Err("Session storage is only available to the Synth app window.".into());
    }
    Ok(())
}

fn entry() -> Result<keyring::Entry, String> {
    let service = if cfg!(debug_assertions) {
        "com.synth.desktop.dev"
    } else {
        "com.synth.desktop"
    };
    keyring::Entry::new(service, "desktop-session")
        .map_err(|_| "Unable to access secure session storage.".into())
}

#[tauri::command]
pub async fn read_desktop_session(
    window: WebviewWindow,
    state: State<'_, SessionStore>,
) -> Result<Credentials, String> {
    check_window(&window)?;
    let lock = state.0.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = lock
            .lock()
            .map_err(|_| "Secure session storage is unavailable.")?;
        match entry()?.get_password() {
            Ok(raw) => {
                let value = serde_json::from_str::<Credentials>(&raw)
                    .map_err(|_| "Saved session is unreadable.")?;
                validate_credentials(&value)?;
                Ok(value)
            }
            Err(keyring::Error::NoEntry) => Ok(Credentials::default()),
            Err(_) => Err(
                "Unable to unlock secure session storage. Unlock your keychain and retry.".into(),
            ),
        }
    })
    .await
    .map_err(|_| "Secure session storage is unavailable.")?
}

#[tauri::command]
pub async fn write_desktop_session(
    window: WebviewWindow,
    state: State<'_, SessionStore>,
    credentials: Credentials,
) -> Result<(), String> {
    check_window(&window)?;
    validate_credentials(&credentials)?;
    let lock = state.0.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = lock
            .lock()
            .map_err(|_| "Secure session storage is unavailable.")?;
        let entry = entry()?;
        if credentials.session.is_none() && credentials.pending_revocations.is_empty() {
            return match entry.delete_credential() {
                Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
                Err(_) => Err("Unable to clear secure session storage.".into()),
            };
        }
        let raw = serde_json::to_string(&credentials).map_err(|_| "Unable to save session.")?;
        entry
            .set_password(&raw)
            .map_err(|_| "Unable to save session securely. Unlock your keychain and retry.".into())
    })
    .await
    .map_err(|_| "Secure session storage is unavailable.")?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn credentials_are_limited_to_session_tokens() {
        let mut value = Credentials::default();
        assert!(validate_credentials(&value).is_ok());
        value
            .pending_revocations
            .push(format!("{}.{}", "a".repeat(32), "b".repeat(43)));
        assert!(validate_credentials(&value).is_ok());
        value.pending_revocations.push("password".into());
        assert!(validate_credentials(&value).is_err());
    }

    #[test]
    fn external_pages_cannot_navigate_the_app_or_read_credentials() {
        for url in [
            "https://synthapp.io/",
            "https://evil.example/",
            "http://tauri.localhost:5000/",
            "https://user@tauri.localhost/",
            "file:///tmp/file",
            "javascript:alert(1)",
        ] {
            assert!(!is_app_url(&tauri::Url::parse(url).unwrap()));
        }
        assert!(is_app_url(
            &tauri::Url::parse("http://tauri.localhost/invite/code").unwrap()
        ));
    }

    #[cfg(windows)]
    #[test]
    fn windows_credentials_persist_across_independent_entries() {
        let name = format!(
            "session-test-{}-{:?}",
            std::process::id(),
            std::time::SystemTime::now()
        );
        let first = keyring::Entry::new("com.synth.desktop.tests", &name).unwrap();
        first.set_password("fake-test-session").unwrap();
        let second = keyring::Entry::new("com.synth.desktop.tests", &name).unwrap();
        let retrieved = second.get_password();
        first.delete_credential().unwrap();
        assert_eq!(retrieved.unwrap(), "fake-test-session");
        assert!(matches!(
            second.get_password(),
            Err(keyring::Error::NoEntry)
        ));
    }
}
