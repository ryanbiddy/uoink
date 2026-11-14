#!/usr/bin/env node
'use strict';

const { main } = require('../lib/main.js');

main(process.argv.slice(2)).then(
  (code) => {
    process.exitCode = code;
  },
  (err) => {
    process.stderr.write(`uoink: ${err && err.message ? err.message : err}\n`);
    process.exitCode = 1;
  }
);
