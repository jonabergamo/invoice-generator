#!/bin/bash

# Diretório onde o template .tex está localizado
TEMPLATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Caminho para o arquivo que armazena o número da fatura
INVOICE_NUMBER_FILE="${TEMPLATE_DIR}/invoice_number.txt"

# Se o arquivo de número de fatura não existir, cria com o valor inicial 1
if [ ! -f "$INVOICE_NUMBER_FILE" ]; then
  echo "1" > "$INVOICE_NUMBER_FILE"
fi

# Lê o último número da fatura e incrementa
INVOICE_NUMBER=$(cat "$INVOICE_NUMBER_FILE")
NEXT_INVOICE_NUMBER=$((INVOICE_NUMBER + 1))

# Atualiza o número da fatura no arquivo
echo "$NEXT_INVOICE_NUMBER" > "$INVOICE_NUMBER_FILE"

# Variáveis para o mês e ano
CURRENT_MONTH=$(date +'%m')  # Mês em formato numérico (01-12)
CURRENT_YEAR=$(date +'%Y')

# Nome do arquivo PDF gerado
PDFNAME="Invoice_${CURRENT_MONTH}_${CURRENT_YEAR}_#${NEXT_INVOICE_NUMBER}.pdf"

# Caminho do template LaTeX
TEX_TEMPLATE="${TEMPLATE_DIR}/invoice_template.tex"

# Verificando se o template .tex existe
if [ ! -f "$TEX_TEMPLATE" ]; then
    echo "Error: LaTeX template not found at $TEX_TEMPLATE"
    exit 1
fi

# Carregar variáveis do arquivo .env (ou arquivo de configuração)
if [ -f "$TEMPLATE_DIR/.env" ]; then
    source "$TEMPLATE_DIR/.env"
else
    echo "Error: .env file not found!"
    exit 1
fi

# Função para escapar as variáveis para o sed
escape_sed() {
    printf '%s' "$1" | sed 's/[&/\]/\\&/g'
}

# Criando um arquivo temporário .tex com as variáveis substituídas
TEMP_TEX="${TEMPLATE_DIR}/invoice_temp.tex"

# Substituindo variáveis do template com as variáveis escapadas
echo "Substituindo variáveis no template..."
sed "s/{{INVOICE_NUMBER}}/${NEXT_INVOICE_NUMBER}/g" "$TEX_TEMPLATE" | \
sed "s/{{CURRENT_YEAR}}/${CURRENT_YEAR}/g" | \
sed "s/{{CURRENT_MONTH}}/${CURRENT_MONTH}/g" | \
sed "s/{{COMPANY_NAME}}/$(escape_sed "$COMPANY_NAME")/g" | \
sed "s/{{COMPANY_ID}}/$(escape_sed "$COMPANY_ID")/g" | \
sed "s/{{BILLING_ADDRESS}}/$(escape_sed "$BILLING_ADDRESS")/g" | \
sed "s/{{BANK_NAME}}/$(escape_sed "$BANK_NAME")/g" | \
sed "s/{{BENEFICIARY_NAME}}/$(escape_sed "$BENEFICIARY_NAME")/g" | \
sed "s/{{SERVICE_TITLE}}/$(escape_sed "$SERVICE_TITLE")/g" | \
sed "s/{{SERVICE_DESC}}/$(escape_sed "$SERVICE_DESC")/g" | \
sed "s/{{CURRENCY}}/$(escape_sed "$CURRENCY")/g" | \
sed "s/{{AMOUNT}}/$(escape_sed "$AMOUNT")/g" | \
sed "s/{{BILL_FROM}}/$(escape_sed "$BILL_FROM")/g" | \
sed "s/{{BILL_TO}}/$(escape_sed "$BILL_TO")/g" | \

sed "s/{{BANK_ADDRESS}}/$(escape_sed "$BANK_ADDRESS")/g" | \
sed "s/{{IBAN}}/$(escape_sed "$IBAN")/g" | \
sed "s/{{SWIFT}}/$(escape_sed "$SWIFT")/g" | \
sed "s/{{INTERMEDIARY_BANK_NAME}}/$(escape_sed "$INTERMEDIARY_BANK_NAME")/g" | \
sed "s/{{INTERMEDIARY_BANK_SWIFT}}/$(escape_sed "$INTERMEDIARY_BANK_SWIFT")/g" | \
sed "s/{{SUPPORT_EMAIL}}/$(escape_sed "$SUPPORT_EMAIL")/g" > "$TEMP_TEX"

# Verifique o conteúdo gerado do arquivo .tex
echo "Arquivo .tex gerado:"
cat "$TEMP_TEX"  # Isso vai ajudar a verificar se a substituição ocorreu corretamente

# Compilando o arquivo .tex para gerar o PDF
pdflatex -output-directory="$TEMPLATE_DIR" "$TEMP_TEX" && \
mv "${TEMPLATE_DIR}/invoice_temp.pdf" "$PDFNAME"

# Limpando os arquivos auxiliares
rm -f "$TEMP_TEX" "${TEMPLATE_DIR}/invoice_temp.aux" "${TEMPLATE_DIR}/invoice_temp.log" "${TEMPLATE_DIR}/invoice_temp.out"


# Verificando se o PDF foi gerado com sucesso
if [ ! -f "$PDFNAME" ]; then
    echo "Error: PDF generation failed. Check the .log fi
