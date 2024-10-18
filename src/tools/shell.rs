use rexpect::session::PtySession;
use rexpect::spawn;
use rexpect::errors::{Error, Result};

pub struct Shell {
    session: PtySession,
}

pub struct Config {
    timeout: u64,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            timeout: 30000,
        }
    }
}

impl Shell {
    pub fn start_shell(config: Config) -> Result<Self> {
        let shell_command = "/bin/bash --noprofile --norc";
        let mut session = spawn(shell_command, Some(config.timeout))?;
        session.send_line("export PS1='#@*'")?;
        session.exp_string("#@*")?;
        session.send_line("stty -icanon -echo")?;
        session.exp_string("#@*")?;
        Ok(Shell { session })
    }

    pub fn execute_command(&mut self, command: &str) -> Result<String> {
        self.session.send_line(command)?;
        let (output, _) = self.session.exp_regex(r"(?m)^#@*")?;
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