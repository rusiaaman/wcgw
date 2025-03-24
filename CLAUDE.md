# Alignment instructions to contribute to this repository

## Hard rules

- Make sure mypy --strict passes for these two folders `uv run mypy --strict src/wcgw src/wcgw_cli`.
- Use `list` directly for typing like `list[str]` no need to import `List`. Same thing for `tuple`, `set`, etc.
- No optional parameters in a function with default values. All parameters must be passed by a caller.
- This library uses `uv` as package manager. To add a package `uv add numpy`. To run pytest `uv run pytest` and so on.

## Coding mantras

### Reduce states and dependencies between the states

- Don't introduce any state unless really necessary.
- If anything can be derived, avoid storing it or passing it.

#### Python `Exception` guideline 1

- Exception thrown inside functions are their hidden extra state which should be avoided.
- Parse don't validate: avoid throwing validation errors by letting the types avoid bad values to be passed in the first place.

### Put burden on type checker not the code reader

- No hidden contracts and assumptions.
- Don't assume any relationship between two states unless it's encoded in the type of the state.
- Any contract should be enforced by the way types are constructed.
- If it's just not possible due to complexity to type in such a way to avoid hidden contract, add in docstring details.

#### Python `Exception` guideline 2

- When you can't avoid it, instead of enforcing the hidden contract as hard failure during runtime, try to return some sensible value instead.
  _Example_
  In PIL adding boxes outside image bounds don't do anything, but they don't fail either, making it a cleaner experience to deal with edge cases.

- A functions signature (along with types) should be enough to understand its purpose.
- This can be achieved by typing the parameters to only take narrow types

### Functions should be as pure as possible

- Avoid mutating mutable input parameters, instead return newly derived values in the output and leave upto the caller to update the state if required.
- It should be clear from function signature what the function computes, this should also enforce the previous point of not updating mutable input parameters.
