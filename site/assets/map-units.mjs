// Display-only conversions. BIN reads/writes and XDF equations stay in raw codes.
export function displayValue(raw,profile,estimated,delta=false){
  return estimated&&profile?raw*profile.slope+(delta?0:profile.offset):raw;
}
export function displayText(value){
  return String(Number(value.toFixed(3)));
}
