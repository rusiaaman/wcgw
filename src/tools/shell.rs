use rexpect::errors::ErrorKind::Timeout;
use rexpect::errors::{Error as RexpectError, Result, ResultExt};
use rexpect::session::{PtyReplSession, PtySession};
use rexpect::{spawn, spawn_bash};
use std::fmt::Display;
use std::io::Write;
use tiktoken_rs::CoreBPE;

use super::render_terminal::render_terminal_output;



#[derive(PartialEq)]
enum BashState {
    WaitingForInput,
    Idle,
}

pub trait Logger {
    fn log(&self, message: &str);
}

pub struct Shell {
    session: PtyReplSession,
    state: BashState,
    logger: Box<dyn Logger>,
    tokenizer: CoreBPE,
}

pub struct Config {
    timeout: u64,
}

impl Default for Config {
    fn default() -> Self {
        Config { timeout: 5000 }
    }
}

#[derive(Debug)]
pub enum ShellError {
    RexpectError(RexpectError),
    ShellWorkflowError(String),
}

impl From<String> for ShellError {
    fn from(error: String) -> Self {
        ShellError::ShellWorkflowError(error)
    }
}

impl From<RexpectError> for ShellError {
    fn from(error: RexpectError) -> Self {
        ShellError::RexpectError(error)
    }
}

pub enum Specials {
    KeyUp,
    KeyDown,
    KeyLeft,
    KeyRight,
    Enter,
    CtrlC,
}

impl Display for Specials {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            Specials::KeyUp => write!(f, "KeyUp"),
            Specials::KeyDown => write!(f, "KeyDown"),
            Specials::KeyLeft => write!(f, "KeyLeft"),
            Specials::KeyRight => write!(f, "KeyRight"),
            Specials::Enter => write!(f, "Enter"),
            Specials::CtrlC => write!(f, "CtrlC"),
        }
    }
}

pub enum AsciiOrSpecial {
    Ascii(Vec<u8>),
    Special(Specials),
}

const WAITING_FOR_INPUT_ERROR: &str = "A command is already running that hasn't exited. NOTE: You can't run multiple shell sessions, likely a previous program is in infinite loop.\nKill the previous program by sending ctrl+c first using `send_ascii`";

impl Shell {
    pub fn start_shell(
        config: Config,
        logger: Box<dyn Logger>,
        tokenizer: CoreBPE,
    ) -> std::result::Result<Self, ShellError> {
        let mut session = spawn_bash(Some(config.timeout))?;
        Ok(Shell {
            session,
            state: BashState::Idle,
            logger,
            tokenizer,
        })
    }

    pub fn execute_command(
        &mut self,
        command: Option<&str>,
        send_ascii: Option<AsciiOrSpecial>,
    ) -> std::result::Result<String, ShellError> {
        if let Some(cmd) = command {
            match self.state {
                BashState::WaitingForInput => {
                    return Err(ShellError::ShellWorkflowError(
                        WAITING_FOR_INPUT_ERROR.to_owned(),
                    ));
                }
                BashState::Idle => {}
            }
            let cmd = cmd.trim();
            if cmd.contains('\n') {
                return Err(ShellError::ShellWorkflowError("Command should not contain newline character in middle. Run only one command at a time.".to_owned()));
            }
            self.logger.log(&format!("$ {}", cmd));
            self.session.send_line(cmd)?;
        } else if let Some(AsciiOrSpecial::Ascii(ascii)) = send_ascii {
            for ch in ascii {
                self.session
                    .writer
                    .write(&[ch])
                    .chain_err(|| "cannot write line to process")?;
            }
            self.session.flush()?;
        } else if let Some(AsciiOrSpecial::Special(special)) = send_ascii {
            match special {
                Specials::KeyUp => self
                    .session
                    .writer
                    .write("\x1B[A".as_bytes())
                    .chain_err(|| "cannot write line to process")?,
                Specials::KeyDown => self
                    .session
                    .writer
                    .write("\x1B[B".as_bytes())
                    .chain_err(|| "cannot write line to process")?,
                Specials::KeyLeft => self
                    .session
                    .writer
                    .write("\x1B[D".as_bytes())
                    .chain_err(|| "cannot write line to process")?,
                Specials::KeyRight => self
                    .session
                    .writer
                    .write("\x1B[C".as_bytes())
                    .chain_err(|| "cannot write line to process")?,
                Specials::Enter => self
                    .session
                    .writer
                    .write("\n".as_bytes())
                    .chain_err(|| "cannot write line to process")?,
                Specials::CtrlC => self
                    .session
                    .writer
                    .write(&[3])
                    .chain_err(|| "cannot write line to process")?,
            };
            self.session.flush()?;
        } else {
            return Err(ShellError::ShellWorkflowError(
                "No command or ascii to send.".to_owned(),
            ));
        }
        self.state = BashState::Idle;
        self.wait_for_output()
    }

    fn wait_for_output(&mut self) -> std::result::Result<String, ShellError> {
        let expected: Result<String> = self.session.wait_for_prompt();
        match expected {
            Err(RexpectError(error_kind, state)) => match error_kind {
                Timeout(_, output, _) => {
                    self.state = BashState::WaitingForInput;
                    let output = self.truncate_output(output)?;
                    let last_line = "(pending)";
                    return Ok(format!("{}\n{}", output, last_line));
                }
                _ => {
                    return Err(ShellError::RexpectError(RexpectError(error_kind, state)));
                }
            },
            Ok(output) => {
                self.state = BashState::Idle;
                println!("output: {:?}", output);
                let output = self.truncate_output(render_terminal_output(output))?;
                println!("output: {}", output);
                let err_code = self.get_exit_code()?;
                let output = format!("{}\n(exit {})", output, err_code);
                return Ok(output);
            }
        }
    }

    fn truncate_output(&self, output: String) -> std::result::Result<String, ShellError> {
        let tokens = self.tokenizer.encode_with_special_tokens(&output);
        if tokens.len() > 2048 {
            let output = self
                .tokenizer
                .decode(tokens[tokens.len() - 2047..].to_vec())
                .unwrap();
            Ok(format!("...(truncated)\n{}", output))
        } else {
            Ok(output)
        }
    }

    pub fn get_exit_code(&mut self) -> Result<i32> {
        self.session.send_line("echo $?")?;
        let mut before = String::new();

        loop {
            match before.trim().parse::<i32>() {
                Err(_) => {
                    println!("before: {:?}", before);
                    before = render_terminal_output(self.session.wait_for_prompt()?);
                }
                Ok(val) => return Ok(val),
            }
        }
    }
}
