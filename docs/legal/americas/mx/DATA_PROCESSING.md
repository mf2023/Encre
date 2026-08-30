# Procesamiento de Datos — México

**Última actualización：22 de agosto de 2026**

**Ámbito de aplicación：** Este documento describe cómo tratamos los datos en los servicios de Dunimd para usuarios ubicados en México. Para usuarios en México, es la única versión aplicable.

> Documentos relacionados：[Aviso de Privacidad](PRIVACY.md) · [Términos de Servicio](TERMS.md) · [Acuerdo de Usuario](USER_AGREEMENT.md) · [Privacidad de Menores](MINORS_PRIVACY.md) · [Directrices de Contenido](CONTENT_GUIDELINES.md)

## Índice

1. [Declaración local-first](#1-declaración-local-first)
2. [Flujos de datos](#2-flujos-de-datos)
3. [Tratamiento por servicio](#3-tratamiento-por-servicio)
4. [Telemetría](#4-telemetría)
5. [Seguridad e incidentes](#5-seguridad-e-incidentes)
6. [Encargados y transferencias](#6-encargados-y-transferencias)
7. [Cambios y contacto](#7-cambios-y-contacto)

---

## 1. Declaración local-first

1.1 Encre Agent funciona localmente：agentes, prompts, respuestas e integraciones permanecen en su dispositivo.

1.2 La telemetría está desactivada por defecto; los prompts y respuestas no se almacenan por defecto.

1.3 El tratamiento fuera de su dispositivo solo ocurre si usted activa servicios en la nube opcionales.

## 2. Flujos de datos

| Dato | Ubicación | Conservación |
|---|---|---|
| Configuraciones de agentes y flujos | Solo dispositivo | Hasta su eliminación |
| Historiales de conversación | Solo dispositivo | Control del usuario |
| Claves API (proveedores externos) | Almacenamiento cifrado local | Hasta su eliminación |
| Solicitudes de inferencia en nube | Servidor, eliminadas tras proceso | Durante la sesión |
| Metadatos de servicio | Servidor | Máx. 30 días |
| Telemetría (opt-in) | Servidor | Máx. 90 días |
| Datos de cuenta (solo servicios en nube) | Servidor | Hasta eliminar la cuenta |

## 3. Tratamiento por servicio

3.1 **PiscesLx：** las solicitudes viajan cifradas y se procesan en memoria; los metadatos（marca temporal, tokens, estado）se eliminan automáticamente tras 30 días.

3.2 **Encre Agent Escritorio/Framework：** sin tratamiento en servidores.

3.3 **Enterprise：** tratamiento bajo contrato de encargo conforme a instrucciones del cliente.

3.4 **Integraciones：** aplican además las políticas de cada plataforma de terceros.

## 4. Telemetría

4.1 Estrictamente opt-in：sin su consentimiento expreso no se envía ningún dato diagnóstico.

4.2 Puede desactivarla en cualquier momento desde la configuración; los datos existentes se eliminan.

## 5. Seguridad e incidentes

5.1 Medidas técnicas：TLS 1.2+ en tránsito, AES-256-GCM en reposo, accesos mínimos.

5.2 Medidas organizativas：confidencialidad, registros y auditorías periódicas.

5.3 Ante incidentes con posible afectación significativa：notificación sin dilación a los titulares y, cuando corresponda, a la autoridad competente, junto con medidas de mitigación.

## 6. Encargados y transferencias

6.1 Los proveedores actúan como encargados bajo obligaciones contractuales de confidencialidad y seguridad equivalentes.

6.2 Las transferencias internacionales se realizan conforme a la ley vigente y, cuando se requiera, con su consentimiento expreso informado en el aviso de privacidad.

## 7. Cambios y contacto

7.1 Los cambios relevantes se publican con al menos 30 días de antelación.

7.2 Contacto：dunimd@outlook.com · dunimd.com

---

*Este documento tiene fines informativos y no constituye asesoría legal.*
