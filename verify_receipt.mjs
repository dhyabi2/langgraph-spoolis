import { readFile } from 'node:fs/promises'
import { verifyOutcomeReceipt } from '@spoolis/receipt-verifier'

const receiptPath = process.argv[2] ?? 'outcome-receipt.json'
const receipt = JSON.parse(await readFile(receiptPath, 'utf8'))
const response = await fetch('https://spoolis.com/.well-known/spoolis-keys.json')
if (!response.ok) throw new Error(`Key fetch failed with HTTP ${response.status}`)

const keys = await response.json()
const trustSet = keys.receipts?.[receipt.environment]
if (!trustSet) throw new Error('No receipt key is published for this environment')

const check = await verifyOutcomeReceipt(receipt, {
  trustSet,
  environment: receipt.environment,
})
if (!check.valid) throw new Error(check.reasons.join(', '))

console.log(JSON.stringify({ authentic: true, earned: receipt.amounts.earned }))

