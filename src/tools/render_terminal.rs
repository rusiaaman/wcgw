use vte::{Parser, Perform};
use std::collections::VecDeque;

// Struct representing the screen for rendering terminal output
struct Screen {
    buffer: VecDeque<String>,
    width: usize,
    height: usize,
}

impl Screen {
    fn new(width: usize, height: usize) -> Self {
        Self {
            buffer: VecDeque::from(vec![String::new(); height]),
            width,
            height,
        }
    }

    fn scroll_up(&mut self) {
        self.buffer.pop_front();
        self.buffer.push_back(String::new());
    }

    fn write_text(&mut self, text: &str) {
        // Check if we need to scroll up before borrowing the line
        if let Some(line) = self.buffer.back() {
            if line.len() + text.len() > self.width {
                self.scroll_up();
            }
        }
        if let Some(line) = self.buffer.back_mut() {
            line.push_str(text);
        }
    }

    fn render(&self) -> String {
        let filtered_lines: Vec<&String> = self
            .buffer
            .iter()
            .rev()
            .skip_while(|line| line.trim().is_empty())
            .collect();
        filtered_lines.into_iter().rev().cloned().collect::<Vec<_>>().join("\n")
    }
}

// Implement the Perform trait to handle terminal escape sequences
struct TerminalEmulator {
    screen: Screen,
}

impl TerminalEmulator {
    fn new(width: usize, height: usize) -> Self {
        Self {
            screen: Screen::new(width, height),
        }
    }

    fn feed(&mut self, text: &str) {
        let mut parser = Parser::new();
        for byte in text.as_bytes() {
            parser.advance(self, *byte);
        }
    }

    fn render(&self) -> String {
        self.screen.render()
    }
}

impl Perform for TerminalEmulator {
    fn print(&mut self, c: char) {
        self.screen.write_text(&c.to_string());
    }

    fn execute(&mut self, byte: u8) {
        // Handle line feed
        if byte == b'\n' {
            self.screen.scroll_up();
        }
    }

}

pub fn render_terminal_output(text: String) -> String {
    // replace all \t with 4 spaces as it's not being rendered by the terminal emulator
    let text = text.replace("\t", "    ");
    let mut emulator = TerminalEmulator::new(160, 500);
    emulator.feed(&text);
    let output = emulator.render();
    // trim all leading whitespace
    output.trim_start().to_string()
}
