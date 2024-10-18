mod tools;
use clap::{Arg, Command};
use tools::shell::Shell;

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

    if let Some(command) = matches.get_one::<String>("shell") {
        match Shell::start_shell(Default::default()) {
            Ok(mut shell) => {
                match shell.execute_command(command) {
                    Ok(output) => println!("Command output: {}", output),
                    Err(e) => eprintln!("Failed to execute command: {}", e),
                }
            }
            Err(e) => eprintln!("Failed to start shell: {}", e),
        }
    }
}
