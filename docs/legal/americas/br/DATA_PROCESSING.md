# Processamento de Dados — Brasil

**Última atualização：22 de agosto de 2026**

**Escopo:** Esta visão geral descreve como a Dunimd processa dados nos serviços destinados ao Brasil. Para usuários no Brasil, este documento é a única versão aplicável.

> Documentos relacionados: [Política de Privacidade](PRIVACY.md) · [Termos de Serviço](TERMS.md) · [Contrato do Usuário](USER_AGREEMENT.md) · [Privacidade de Menores](MINORS_PRIVACY.md) · [Diretrizes de Conteúdo](CONTENT_GUIDELINES.md)

## Índice

1. [Declaração local-first](#1-declaração-local-first)
2. [Fluxos de dados](#2-fluxos-de-dados)
3. [Tratamento por serviço](#3-tratamento-por-serviço)
4. [Telemetria](#4-telemetria)
5. [Transferência internacional](#5-transferência-internacional)
6. [Segurança e comunicação de incidentes](#6-segurança-e-comunicação-de-incidentes)
7. [Alterações e contato](#7-alterações-e-contato)

---

## 1. Declaração local-first

1.1 O Encre Agent foi projetado para operar localmente: dados de agentes, prompts, respostas e histórico ficam no seu dispositivo.

1.2 Telemetria desativada por padrão; armazenamento de prompts e respostas desativado por padrão.

## 2. Fluxos de dados

| Dado | Local | Retenção |
|---|---|---|
| Configurações de agentes e fluxos | Somente dispositivo | Até exclusão |
| Histórico de conversas | Somente dispositivo | Controle do usuário |
| Chaves de API de provedores | Armazenamento criptografado no dispositivo | Até exclusão |
| Solicitações de inferência em nuvem | Memória do servidor | Descartadas após processamento |
| Metadados de serviço | Servidor | Máx. 30 dias |
| Telemetria (opt-in) | Servidor | Máx. 90 dias |
| Dados de conta (serviços em nuvem) | Servidor | Até exclusão da conta |

## 3. Tratamento por serviço

3.1 **PiscesLx:** solicitações trafegam cifradas e são processadas em memória; metadados (carimbo de data/hora, tokens, status) retidos por até 30 dias e depois eliminados.

3.2 **Encre Agent Desktop/Framework:** nenhum tratamento em servidor.

3.3 **Dunimd Enterprise:** operamos como operador, sob contrato com cláusulas específicas (arts. 39 e 44 da LGPD), incluindo relatório de impacto (RIPD) quando aplicável.

## 4. Telemetria

4.1 Estritamente opt-in: nada é enviado antes do consentimento expresso.

4.2 Desativável a qualquer momento nas configurações; dados existentes são eliminados após a desativação.

## 5. Transferência internacional

5.1 Quando houver transferência internacional, aplicamos as hipóteses dos arts. 33–36 da LGPD — em particular as **cláusulas-padrão aprovadas pela ANPD (Resolução CD/ANPD nº 19/2024)** — e garantias adicionais documentadas.

## 6. Segurança e comunicação de incidentes

6.1 Medidas técnicas: TLS 1.2+ em trânsito, AES-256-GCM em repouso, acesso mínimo.

6.2 Medidas organizacionais: sigilo, registros de acesso, revisões periódicas.

6.3 **Incidentes:** comunicaremos à ANPD e aos titulares conforme prazos fixados pela autoridade (art. 48 da LGPD e regulamentação).

## 7. Alterações e contato

7.1 Alterações serão publicadas com pelo menos **30 dias** de antecedência.

7.2 Contato: dunimd@outlook.com · dunimd.com · ANPD: gov.br/anpd

---

*Este documento tem caráter informativo e não constitui aconselhamento jurídico.*
