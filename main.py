import time
from machine import I2C,RTC,Timer,Pin,PWM
import lps22
import icm20948
from buzzer import *

####################
#### Constantes ####
####################
DEPOTAGE        = False # Activation de la version avec depotage (sans trappe parachute)
ACC_IMU         = True  # activation de l'information d'accélaration par l'IMU sinon par le contacteur mécanique
BUZZER_ENABLE   = True # activation du buzzer
ACC_THESHOLD    = 1     # seuil de l'accélération pour détecter le décollage [g]
TIMEOUT_FALLING = 8000  # temps après lequel la fusée passe en mode chute libre [ms]
SERVO_OPEN      = 800   # [us]
SERVO_CLOSE     = 1400  # [us]

#####################
#### Declaration ####
#####################
# Declaration du bus de communication I2C
i2c = I2C(1,freq=400000)  # default assignment: scl=Pin(7), sda=Pin(6)

# Declaration des capteurs
lps22 = lps22.LPS22HB(i2c)
imu = icm20948.ICM20948(i2c_bus=i2c)

# Declaration du timer
timerAcq = Timer()

# Declaration de l'horloge temps réel (RTC)
rtc = RTC()

# Declaration de la pin du parachute
portePara = 0
if DEPOTAGE is False:
    portePara = PWM(Pin(10, Pin.OUT))
    portePara.freq(50) # 50 Hz
# portePara.calibration(700, 2400, 1510, 2500, 2000) # Min pulse, max pulse, middle pulse, 90 deg pulse, 100 speed

# Declaration de la pin de l'interrupteur d'accélération
accPin = Pin(28, Pin.IN)

###################
#### Variables ####
###################
# Initialisation des variables
isSampling = False
isLaunched = False
isFalling = False
tempsDecollage = 0

###################
#### Fonctions ####
###################
# Initialisation de la carte
def InitBoard():
    # Initialisation de la date/heure
    rtc.datetime((2020,1,1,0,0,0,0,0))

    # Initialisation du timer d'acquisition
    timerAcq.init(freq=10, mode=Timer.PERIODIC, callback=Sampling)


# Activation de l'acquisition des données
def Sampling(timer):
    global isSampling
    isSampling=True

def FermetureParachute():
    if DEPOTAGE is False:
        global portePara
        portePara.duty_ns(SERVO_CLOSE*1000)

def OuvertureParachute():
    if DEPOTAGE is False:
        global portePara
        portePara.duty_ns(SERVO_OPEN*1000)

# Main fonction
if __name__ == '__main__':

    # Ouvre la trappe parachute au démarrage si besoin
    OuvertureParachute()

    # Attente pour placer la trappe parachute si besoin
    InitMusic(BUZZER_ENABLE)
    time.sleep(3)
    
    # Fermeture de la trappe parachute si besoin
    FermetureParachute()

    # Initialisation des fonctions d'acquisitions
    InitBoard()

    # Ouvre un fichier pour l'écriture des données
    filePlatform = open("data_platform.txt","a", encoding="utf-8")
    fileCu = open("data_cu.txt","a", encoding="utf-8")

    # Initialisation du temps initial
    tempsMsDebut = time.ticks_ms()

    # Configure le buzzer pour faire un son specifique avant décollage
    SetBuzzer(BUZZER_ENABLE, freq=1000, tps=2)

    while True:
        if isSampling is True:
            # Acquisition du temps actuel
            tempsAcq = time.ticks_diff(time.ticks_ms(), tempsMsDebut)/1000 + 1

            # Acquisitions des capteurs
            ax, ay, az, gx, gy, gz = imu.read_accelerometer_gyro_data()
            mx, my, mz = imu.read_magnetometer_data()
            pressure = lps22.read_pressure()
            temp = lps22.read_temperature()

            # Si l'acceleration dépasse le seuil ou que la pin d'accélération est appuyée, et que le décollage n'est pas encore arrivé, il y a eu décollage
            if ((ay > ACC_THESHOLD and ACC_IMU is True) or (accPin.value() == 0 and ACC_IMU is False)) and (isLaunched is False):
                # Changement de status de l'indicateur de decollage
                isLaunched = True
                # Sauvegarde du temps de décollage
                tempsDecollage = time.ticks_ms()
                # Changement du son du buzzer
                SetBuzzer(BUZZER_ENABLE, freq=1500, tps=1)
                # Acquisition du temps du composant RTC
                tempsRtc = rtc.datetime()
                # Ecriture du temps actuel du decollage dans le fichier
                filePlatform.write(f"Decollage: {tempsRtc[4]:d}h{tempsRtc[5]:d}m{tempsRtc[6]:d}s{(tempsAcq % 1)*100:02.0f}\n")
                filePlatform.write("Temps (s) / Pression (mBar) / temperature (°C) / acc X (g/s^2) / acc Y (g/s^2) / acc Z (g/s^2)\n")
                # Affichage sur la console
                print('Decollage !')

            # Si le decollage est passé et que la chute libre n'est pas encore arrivé
            if (isLaunched is True) and (isFalling is False):
                # Si le timer de chute libre est dépassé
                if (time.ticks_ms()-tempsDecollage > TIMEOUT_FALLING):
                    # Ouverture de la trappe parachute si besoin 
                    OuvertureParachute()
                    # Changement de status de chute libre
                    isFalling = True
                    # Changement du son du buzzer
                    SetBuzzer(BUZZER_ENABLE, freq=2000, tps=0.5)
                    # Acquisition du temps du composant RTC
                    tempsRtc = rtc.datetime()
                    # Ecriture du temps actuel du debut de la chute libre dans le fichier
                    filePlatform.write(f"Chute libre: {tempsRtc[4]:d}h{tempsRtc[5]:d}m{tempsRtc[6]:d}s{(tempsAcq % 1)*100:02.0f}\n")
                    # Affichage sur la console
                    print('Chute libre !')

            # Si la fusee est en chute libre
            # if isFalling is True:
                # isLaunched = False

            # Si le decollage est passé, on enregistre les données
            if isLaunched is True:
                # Mise en forme des données à écrire sur le fichier (temps, pression, température, accélération x,y,z)
                dataFilePlat = f"{tempsAcq:.2f} {pressure:.1f} {temp:.1f} {ax:.2f} {ay:.2f} {az:.2f}\n"
                # Ecriture sur le fichier
                filePlatform.write(dataFilePlat)

                ############################################################
                ########## Mettre ici le code de la charge utile  ##########
                ########## qui va se dérouler après le décollage  ##########
                ############################################################

                # Mise en forme des données à écrire sur le fichier
                # Par exemple: le temps et la température
                dataCu = f"{tempsAcq:.2f} {temp:.1f}\n"

                # Ecriture des données dans le fichier data_cu.txt
                fileCu.write(dataCu)

                ############################################################
                ########## Fin du code de la charge utile         ##########
                ############################################################

            # Reinitialisation de l'indicateur pour le timer d'acquisition
            isSampling = False

            # Affichage des resultats sur la console
            tempsRtc = rtc.datetime()
            print(f'\nTime:        {tempsRtc[4]:d}h{tempsRtc[5]:d}m{tempsRtc[6]:d}s / {tempsAcq:.2f}')
            print(f'Acceleration:  X = {ax:.2f} , Y = {ay:.2f} , Z = {az:.2f}')
            print(f'Gyroscope:     X = {gx:.2f} , Y = {gy:.2f} , Z = {gz:.2f}')
            print(f'Magnetic:      X = {mx:.2f} , Y = {my:.2f} , Z = {mz:.2f}')
            print(f'Pressure:      P = {pressure:.2f} hPa')
            print(f'Temperature:   T = {temp:.2f} °C')
