//! Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
//!
//! This file is part of Yim.
//! The Yim project belongs to the Dunimd Team.
//!
//! Licensed under the Apache License, Version 2.0 (the "License");
//! You may not use this file except in compliance with the License.
//! You may obtain a copy of the License at
//!
//!     http://www.apache.org/licenses/LICENSE-2.0
//!
//! Unless required by applicable law or agreed to in writing, software
//! distributed under the License is distributed on an "AS IS" BASIS,
//! WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//! See the License for the specific language governing permissions and
//! limitations under the License.
//! 
//! DISCLAIMER: Users must comply with applicable AI regulations.
//! Non-compliance may result in service termination or legal liability.

use serde::{Deserialize, Serialize};
use std::process::Command;
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

#[derive(Serialize, Deserialize, Debug)]
pub struct ShellResult {
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
}

pub fn execute_shell(
    command: &str,
    cwd: Option<&str>,
    timeout_secs: u64,
) -> Result<ShellResult, String> {
    let mut cmd = if cfg!(target_os = "windows") {
        let mut c = Command::new("cmd");
        c.args(["/C", command]);
        c
    } else {
        let mut c = Command::new("sh");
        c.args(["-c", command]);
        c
    };

    if let Some(dir) = cwd {
        cmd.current_dir(dir);
    }

    let (tx, rx) = mpsc::channel();
    let cmd_str = command.to_owned();

    thread::spawn(move || {
        let result = cmd
            .output()
            .map_err(|e| format!("Error executing command: {}", e));
        let _ = tx.send(result);
    });

    match rx.recv_timeout(Duration::from_secs(timeout_secs)) {
        Ok(output_result) => {
            let output = output_result?;
            Ok(ShellResult {
                stdout: String::from_utf8_lossy(&output.stdout).to_string(),
                stderr: String::from_utf8_lossy(&output.stderr).to_string(),
                exit_code: output.status.code().unwrap_or(-1),
            })
        }
        Err(_) => Err(format!("Command timed out after {} seconds: {}", timeout_secs, cmd_str)),
    }
}