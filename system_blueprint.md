# Loan EMI Calculator CLI Tool Technical Specification
=====================================================

## Overview
-----------

The Loan EMI Calculator CLI tool is designed to calculate the Equated Monthly Installment (EMI) for a loan based on the principal amount, interest rate, and tenure. The tool will also generate an amortization schedule printout.

## Requirements
------------

### Functional Requirements

1. **User Input**: The tool shall accept the following user inputs:
	* Principal amount (numeric value)
	* Interest rate (numeric value in percentage)
	* Tenure (numeric value in months or years)
2. **EMI Calculation**: The tool shall calculate the EMI using the formula:
	* EMI = (P x R x (1 + R)^N) / ((1 + R)^N - 1)
	* Where:
		+ P = Principal amount
		+ R = Monthly interest rate (annual interest rate / 12)
		+ N = Number of installments (tenure in months)
3. **Amortization Schedule**: The tool shall generate an amortization schedule printout, including:
	* Month/Year
	* Payment (EMI)
	* Interest Paid
	* Principal Paid
	* Outstanding Balance
4. **Error Handling**: The tool shall handle the following errors:
	* Invalid user input (non-numeric values, negative values, etc.)
	* Division by zero errors

### Non-Functional Requirements

1. **Performance**: The tool shall respond to user input within 1 second.
2. **Security**: The tool shall not store any user input data.
3. **Usability**: The tool shall provide a user-friendly interface with clear instructions and feedback.

## Design
--------

### Architecture

The tool shall be built using a command-line interface (CLI) architecture, with the following components:

1. **Input Handler**: Responsible for handling user input and validating data.
2. **EMI Calculator**: Responsible for calculating the EMI using the formula.
3. **Amortization Schedule Generator**: Responsible for generating the amortization schedule printout.
4. **Error Handler**: Responsible for handling errors and providing feedback to the user.

### Data Storage

The tool shall not store any user input data. All calculations shall be performed in memory.

## Implementation
--------------

### Programming Language

The tool shall be implemented in Python 3.x, using the following libraries:

1. **`argparse`**: For handling user input and providing a CLI interface.
2. **`tabulate`**: For generating the amortization schedule printout in a tabular format.

### Code Structure

The tool shall consist of the following modules:

1. **`main.py`**: The entry point of the tool, responsible for handling user input and invoking the EMI calculator and amortization schedule generator.
2. **`emi_calculator.py`**: Responsible for calculating the EMI using the formula.
3. **`amortization_schedule.py`**: Responsible for generating the amortization schedule printout.
4. **`error_handler.py`**: Responsible for handling errors and providing feedback to the user.

## Testing
-------

### Unit Tests

The tool shall include unit tests for the following components:

1. **EMI Calculator**: To verify that the EMI calculation is accurate.
2. **Amortization Schedule Generator**: To verify that the amortization schedule printout is correct.

### Integration Tests

The tool shall include integration tests to verify that the entire system works as expected, including:

1. **User Input Handling**: To verify that the tool handles user input correctly.
2. **Error Handling**: To verify that the tool handles errors correctly.

## Deployment
---------

### Packaging

The tool shall be packaged as a Python package, using the following tools:

1. **`setuptools`**: For building and distributing the package.
2. **`pip`**: For installing the package.

### Installation

The tool shall be installed using the following command:
```bash
pip install loan-emi-calculator
```
### Usage

The tool shall be used by running the following command:
```bash
loan-emi-calculator --principal <amount> --interest-rate <rate> --tenure <months/years>
```
Example:
```bash
loan-emi-calculator --principal 100000 --interest-rate 10 --tenure 12
```