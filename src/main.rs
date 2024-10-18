mod tools;
use clap::{Arg, Command};
use tiktoken_rs::get_bpe_from_model;
use tools::shell::Shell;
use colored::Colorize;

struct Logger;

impl tools::shell::Logger for Logger {
    fn log(&self, message: &str) {
        println!("{}", message.magenta());
    }
}

fn main() {
    let matches = Command::new("wcgw")
        .about("A Rust CLI tool")
        .arg(
            Arg::new("shell")
                .long("shell")
                .num_args(1)
                .help("Execute a shell command"),
        )
        .get_matches();

    let tokenizer = get_bpe_from_model("gpt-4o").unwrap();
    if let Some(command) = matches.get_one::<String>("shell") {
        match Shell::start_shell(Default::default(), Box::new(Logger), tokenizer) {
            Ok(mut shell) => {
                match shell.execute_command(Some(command.as_str()), None) {
                    Ok(output) => println!("Command output: {}", output),
                    Err(e) => eprintln!("Failed to execute command: {:?}", e),
                }
            }
            Err(e) => eprintln!("Failed to start shell: {:?}", e),
        }
    }
}
