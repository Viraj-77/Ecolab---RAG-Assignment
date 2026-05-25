# Coffee Shop ArchiMate Architecture

## Project Overview

This project shows a simple **Coffee Shop Architecture** using ArchiMate.

The diagram explains how a customer buys coffee, how the business process works, how the payment application supports the process, and what technology is used in the background.

The model is divided into three main layers:

1. Business Layer

2. Application Layer

3. Technology Layer

---

## 1. Business Layer

The Business Layer shows the real-world coffee shop process.

### Main Business Actors

- Customer

- Barista

### Main Business Process

- Take Payment & Serve Coffee

### Business Service

- Contactless Coffee Purchase

### Business Object

- Cup of Coffee

### Business Flow

```text

Customer

   ↓

Take Payment & Serve Coffee

   ↓

Contactless Coffee Purchase

   ↓

Cup of Coffee