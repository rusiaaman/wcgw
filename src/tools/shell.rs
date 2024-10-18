use rexpect::session::PtySession;
use rexpect::spawn;
use rexpect::errors::{Error as RexpectError, Result, ResultExt};
use rexpect::errors::ErrorKind::Timeout;

use std::error::Error;
use std::fmt::Display;
use std::io::Write;

#[derive(PartialEq)]
enum BashState {
    Idle,
    WaitingForInput,
    Running,
}


pub trait Logger {
    fn log(&self, message: &str);
}

pub struct Shell {
    session: PtySession,
    config: Config,
    state: BashState,
    logger: Box<dyn Logger>,
}

pub struct Config {
    timeout: u64,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            timeout: 5000
        }
    }
}

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
    Special(Specials)
}

const WAITING_FOR_INPUT_ERROR: &str = "A command is already running that hasn't exited. NOTE: You can't run multiple shell sessions, likely a previous program is in infinite loop.
                    Kill the previous program by sending ctrl+c first using `send_ascii`";

impl Shell {
    pub fn start_shell(config: Config, logger: Box<dyn Logger>) -> std::result::Result<Self, ShellError> {
        let shell_command = "/bin/bash --noprofile --norc";
        let mut session = spawn(shell_command, Some(config.timeout))?;
        session.send_line("export PS1='#@*'")?;
        session.exp_string("#@*")?;
        session.send_line("stty -icanon -echo")?;
        session.exp_string("#@*")?;
        Ok(Shell {
            session,
            state: BashState::Idle,
            logger,
            config,
        })
    }

    pub fn execute_command(&mut self, command: Option<&str>, send_ascii: Option<AsciiOrSpecial>) -> std::result::Result<String, ShellError> {
        if let Some(cmd) = command {
            if self.state == BashState::WaitingForInput {
                return Err(ShellError::ShellWorkflowError(WAITING_FOR_INPUT_ERROR.to_owned()));
            }
            let cmd = cmd.trim();
            if cmd.contains('\n') {
                return Err(ShellError::ShellWorkflowError("Command should not contain newline character in middle. Run only one command at a time.".to_owned()));
            }
            self.logger.log(&format!("$ {}", cmd));
            self.session.send_line(cmd)?;
            
        } else if let Some(AsciiOrSpecial::Ascii(ascii)) = send_ascii {
            for ch in ascii {
                self.session.writer.write(&[ch]).chain_err(|| "cannot write line to process")?;
            }
        } else if let Some(AsciiOrSpecial::Special(special)) = send_ascii {
            match special {
                Specials::KeyUp => self.session.writer.write("\033[A".as_bytes()).chain_err(|| "cannot write line to process")?,
                Specials::KeyDown => self.session.writer.write("\033[B".as_bytes()).chain_err(|| "cannot write line to process")?,
                Specials::KeyLeft => self.session.writer.write("\033[D".as_bytes()).chain_err(|| "cannot write line to process")?,
                Specials::KeyRight => self.session.writer.write("\033[C".as_bytes()).chain_err(|| "cannot write line to process")?,
                Specials::Enter => self.session.writer.write("\n".as_bytes()).chain_err(|| "cannot write line to process")?,
                Specials::CtrlC => self.session.writer.write(&[3]).chain_err(|| "cannot write line to process")?,
            };
        }
        else {
            return Err(ShellError::ShellWorkflowError("No command or ascii to send.".to_owned()));
        }
        self.state = BashState::Running;
        self.wait_for_output()
    }

    fn wait_for_output(&mut self) -> std::result::Result<String, ShellError> {        

        if let Err(RexpectError(error_kind, state)) = self.session.exp_string("#@*") {
            if let Timeout(_, _, _) = error_kind {
                self.state = BashState::WaitingForInput;
                return Err(ShellError::ShellWorkflowError("Timeout waiting for command output.".to_owned()));
            }
            return Err(ShellError::RexpectError(RexpectError(error_kind, state)));
        }
        self.state = BashState::Idle;
        let output = self.session.exp_string("#@*")?;
        Ok(output)
    }
    

    pub fn get_exit_code(&mut self) -> Result<i32> {
        self.session.send_line("echo $?")?;
        let mut before = String::new();
        
        loop {
            match before.trim().parse::<i32>() {
                Err(_) => {
                    // Consume all previous output
                    self.session.exp_string("#@*")?;
                    before = self.session.exp_string("#@*")?;
                }
                Ok(val) => { 
                    return Ok(val)
                }
            }
        }
    }
}
