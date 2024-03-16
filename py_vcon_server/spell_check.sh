#!/bin/sh
file_list="README.md"
for file in $file_list
  do
  echo "Checking spelling in $file"
  spell -d dictionary.txt $file  | sort | uniq
  echo "---------------"
  done


